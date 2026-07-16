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


# Fields shown to the classifier as incident content. AI_TransferredTo is the
# routing LABEL and is deliberately excluded so classification is a fair prediction.
_CONTENT_FIELDS = [
    "Severity", "Product", "ticket_category", "Summary", "Investigation",
    "AI_ProblemStage", "AI_KeyLog", "AI_Conclusion", "AI_Solution",
]


def _normalize_ticket(raw) -> dict:
    """Map an icm-triage ticket into {id, title, owning_team, text, label, raw}."""
    if isinstance(raw, str):
        return {"id": raw, "title": "", "owning_team": "", "text": raw}
    if not isinstance(raw, dict):
        return {"id": "", "title": "", "owning_team": "", "text": str(raw)}

    parts = [f"{k}: {raw[k]}" for k in _CONTENT_FIELDS if raw.get(k)]
    return {
        "id": str(raw.get("IncidentId") or raw.get("id") or ""),
        "title": raw.get("Title") or raw.get("title") or "",
        "owning_team": raw.get("OwningTeamName") or "",
        "text": "\n".join(parts) or json.dumps(raw, ensure_ascii=False),
        "label": raw.get("AI_TransferredTo") or "",   # ground truth, for review only
        "raw": raw,
    }


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
                owning_team=cls.get("owning_team"),
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
        tgt = f" → {d['owning_team']}" if d.get("owning_team") else ""
        lines.append(f"**{d['category']}{tgt}** — {d['reasoning']}\n")
        for a in d["proposed_actions"]:
            lines.append(f"- `{a['kind']}` → **{a['target']}**")
            lines.append(f"  > {a['content']}")
        lines.append("")
    return "\n".join(lines)
