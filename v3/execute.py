"""
Phase 2 — EXECUTE. Read output/review.json and perform ONLY the actions on
decisions marked "approved": true, via your MCP tools.

  send_email      -> TOOL_NAMES["send_email"]
  post_discussion -> TOOL_NAMES["post_discussion"]
  reboot_server   -> no MCP tool yet: logged as a manual/TODO step

Adjust the arg dicts below to match your MCP tools' input schemas.
"""

import json
from pathlib import Path

from mcp_tools import call_tool
from registry import TOOL_NAMES

REVIEW_JSON = Path(__file__).resolve().parent / "output" / "review.json"


async def _run_action(action: dict, ticket_id: str):
    kind, target, content = action["kind"], action["target"], action.get("content", "")

    if kind == "send_email":
        # TODO: match your send_email tool's schema (to/subject/body).
        return await call_tool(TOOL_NAMES["send_email"], {
            "to": target,
            "subject": f"[IcM {ticket_id}] Routed for your team",
            "body": content,
        })

    if kind == "post_discussion":
        # TODO: match your post_discussion tool's schema (incident_id/comment).
        return await call_tool(TOOL_NAMES["post_discussion"], {
            "incident_id": target or ticket_id,
            "comment": content,
        })

    if kind == "reboot_server":
        print(f"   🖥️  MANUAL: reboot '{target}' (no reboot MCP tool wired). {content}")
        return "manual-step"

    print(f"   ⚠️  Unknown action kind: {kind}")
    return None


async def execute_reviewed() -> None:
    if not REVIEW_JSON.exists():
        print(f"❌ {REVIEW_JSON} not found. Run: python main.py triage")
        return

    decisions = json.loads(REVIEW_JSON.read_text(encoding="utf-8"))
    approved = [d for d in decisions if d.get("approved")]
    print(f"▶️  Executing {len(approved)} approved / {len(decisions)} total decisions")

    for d in approved:
        tid = d["ticket_id"]
        print(f"\n🎫 {tid} ({d['category']})")
        for action in d.get("proposed_actions", []):
            try:
                result = await _run_action(action, tid)
                print(f"   ✅ {action['kind']} → {action['target']}: {str(result)[:120]}")
            except Exception as e:
                print(f"   ❌ {action['kind']} failed: {e}")

    print("\n✅ Execute phase complete.")
