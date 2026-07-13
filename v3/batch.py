"""
Phase 1 — TRIAGE. Pull the day's tickets from MCP, classify + draft actions for
each, and write a human review file. Nothing is executed here.

Output:
  output/review.json   <- edit "approved": true on the ones you want executed
  output/review.md     <- readable summary
"""

import json
from pathlib import Path

from mcp_tools import call_tool
from graph import build_app
from schemas import TicketDecision
from registry import TOOL_NAMES, GET_TICKETS_ARGS

OUTPUT_DIR = Path(__file__).resolve().parent / "output"
REVIEW_JSON = OUTPUT_DIR / "review.json"
REVIEW_MD = OUTPUT_DIR / "review.md"


def _normalize_ticket(raw) -> dict:
    """
    Map YOUR MCP's ticket shape into {id, title, text, ...}.
    Adjust the field names here to match what your get_tickets tool returns.
    """
    if isinstance(raw, str):
        return {"id": raw, "title": "", "text": raw}
    if isinstance(raw, dict):
        return {
            "id": str(raw.get("id") or raw.get("IncidentId") or raw.get("incident_id") or ""),
            "title": raw.get("title") or raw.get("Title") or "",
            "text": raw.get("text") or raw.get("summary") or raw.get("Summary") or json.dumps(raw),
            "server": raw.get("server") or raw.get("OccurringDeviceName"),
            "raw": raw,
        }
    return {"id": "", "title": "", "text": str(raw)}


async def fetch_tickets() -> list[dict]:
    """Call the get_tickets MCP tool and normalize the result to a list of tickets."""
    result = await call_tool(TOOL_NAMES["get_tickets"], GET_TICKETS_ARGS)
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except json.JSONDecodeError:
            result = [result]
    if isinstance(result, dict):
        result = result.get("tickets") or result.get("value") or [result]
    tickets = [_normalize_ticket(r) for r in result]
    print(f"📥 Fetched {len(tickets)} tickets")
    return tickets


async def triage_batch() -> list[dict]:
    app = build_app()
    tickets = await fetch_tickets()

    decisions: list[dict] = []
    for t in tickets:
        try:
            final = await app.ainvoke({"ticket": t})
            cls = final["classification"]
            decision = TicketDecision(
                ticket_id=t.get("id", ""),
                title=t.get("title", ""),
                category=cls["category"],
                target_team=cls.get("target_team"),
                reasoning=cls.get("reasoning", ""),
                proposed_actions=final["proposed_actions"],
                approved=False,
            )
            decisions.append(decision.model_dump())
        except Exception as e:
            print(f"❌ Failed on ticket {t.get('id')}: {e}")

    OUTPUT_DIR.mkdir(exist_ok=True)
    REVIEW_JSON.write_text(json.dumps(decisions, indent=2, ensure_ascii=False), encoding="utf-8")
    REVIEW_MD.write_text(_render_md(decisions), encoding="utf-8")
    print(f"\n📝 Wrote {len(decisions)} decisions to {REVIEW_JSON}")
    print(f"   Review {REVIEW_MD}, set \"approved\": true on the ones to run, then: python main.py execute")
    return decisions


def _render_md(decisions: list[dict]) -> str:
    lines = ["# IcM triage review\n", "Set `approved: true` in review.json for actions to execute.\n"]
    for d in decisions:
        lines.append(f"## {d['ticket_id']} — {d['title']}")
        tgt = f" → {d['target_team']}" if d.get("target_team") else ""
        lines.append(f"**{d['category']}{tgt}** — {d['reasoning']}\n")
        for a in d["proposed_actions"]:
            lines.append(f"- `{a['kind']}` → **{a['target']}**")
            lines.append(f"  > {a['content']}")
        lines.append("")
    return "\n".join(lines)
