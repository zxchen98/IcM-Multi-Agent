"""
Phase 2 — EXECUTE (MVP: report-only).

The MVP has no action backend wired: there is no mail MCP to actually send the
route emails, and infra remediation is a manual on-call step. So this phase reads
output/review.json and prints the actions you APPROVED, ready to send/perform by
hand.

To make it actually act later:
  - add a mail MCP server to config/mcp_servers.json + registry.TOOL_NAMES,
  - then dispatch "send_email" / "handle_infra" here via mcp_tools.call_tool(...).
"""

import json
from pathlib import Path

REVIEW_JSON = Path(__file__).resolve().parent / "output" / "review.json"


async def execute_reviewed() -> None:
    if not REVIEW_JSON.exists():
        print(f"[error] {REVIEW_JSON} not found. Run: python main.py triage")
        return

    decisions = json.loads(REVIEW_JSON.read_text(encoding="utf-8"))
    approved = [d for d in decisions if d.get("approved")]
    print(f"[execute] {len(approved)} approved / {len(decisions)} total decisions "
          f"(MVP is report-only — nothing is sent)\n")

    for d in approved:
        print(f"# {d['ticket_id']} ({d['category']})")
        for a in d.get("proposed_actions", []):
            if a["kind"] == "send_email":
                print(f"  EMAIL -> {a['target']}\n    {a['content']}\n")
            elif a["kind"] == "handle_infra":
                print(f"  INFRA (our team) -> incident {a['target']}\n    {a['content']}\n")
            else:
                print(f"  {a['kind']} -> {a['target']}: {a['content']}\n")

    print("[execute] Done. Send the emails / perform the infra actions above manually.")
