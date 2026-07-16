"""
Per-ticket triage graph — BINARY routing:

    START -> classify ─▶ infra?  ── yes ─▶ infra_branch   (our team fixes it)   -> END
                                  └─ no  ─▶ owner_branch   (email the owning team) -> END

`classify` is one structured-output LLM call. Each branch DRAFTS its action
(propose mode) — nothing is executed here. batch.py runs many tickets through
this graph and writes output/review.json.
"""

from typing import Optional, Literal
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, START, END
from langgraph.types import Command

from llm import get_model
from schemas import TriageState
from registry import (
    INFRA_CRITERIA, CLASSIFY_INSTRUCTIONS, OUR_TEAM, OWNER_EMAILS, FALLBACK_EMAIL,
)


def _ticket_text(ticket: dict) -> str:
    return (
        f"Incident ID: {ticket.get('id', '?')}\n"
        f"Title: {ticket.get('title', '')}\n"
        f"Current owning team (as-is): {ticket.get('owning_team', 'unknown')}\n"
        f"Details:\n{ticket.get('text', '')}"
    )


class Classification(BaseModel):
    """Binary triage decision."""
    category: Literal["infra", "route_to_owner"] = Field(
        ..., description="infra = our team fixes it; route_to_owner = hand off to owning team"
    )
    owning_team: Optional[str] = Field(
        None, description="the team that owns this incident, when category == route_to_owner; else null"
    )
    reasoning: str = Field(..., description="one-sentence justification")


async def _draft(instruction: str) -> str:
    resp = await get_model().ainvoke([HumanMessage(content=instruction)])
    return resp.content.strip()


def _resolve_email(team: Optional[str]) -> str:
    """Map an owning-team name to an email (case-insensitive), else the fallback."""
    if team:
        for name, email in OWNER_EMAILS.items():
            if name.lower() == team.lower():
                return email
    return FALLBACK_EMAIL


# --------------------------------------------------------------------------- nodes
async def classify(state: TriageState):
    ticket = state["ticket"]
    prompt = (
        f"{CLASSIFY_INSTRUCTIONS}\n\n{INFRA_CRITERIA}\n\n"
        f"Incident:\n{_ticket_text(ticket)}"
    )
    result = await get_model().with_structured_output(Classification).ainvoke(
        [HumanMessage(content=prompt)]
    )
    cls = result.model_dump()
    goto = "infra_branch" if cls["category"] == "infra" else "owner_branch"
    print(f"[triage] {ticket.get('id','?')} -> {cls['category']}"
          f"{' / ' + str(cls['owning_team']) if cls.get('owning_team') else ''}: {cls['reasoning']}")
    return Command(goto=goto, update={"classification": cls})


async def infra_branch(state: TriageState):
    """OUR team owns it -> draft a short handling note (reboot / on-call action)."""
    t, cls = state["ticket"], state["classification"]
    note = await _draft(
        f"Write a short IcM handling note (under 80 words) for incident {t.get('id')} "
        f"('{t.get('title','')}'). State that {OUR_TEAM} owns this as an infra/server issue "
        f"and will remediate (e.g. reboot/restart the affected node) directly. "
        f"Rationale: {cls['reasoning']}. Keep it professional."
    )
    actions = [{"kind": "handle_infra", "target": str(t.get("id", "")), "content": note}]
    return Command(goto=END, update={"proposed_actions": actions})


async def owner_branch(state: TriageState):
    """Not ours -> draft an email to the owning team."""
    t, cls = state["ticket"], state["classification"]
    team = cls.get("owning_team") or t.get("owning_team") or "the owning team"
    email_to = _resolve_email(cls.get("owning_team") or t.get("owning_team"))
    body = await _draft(
        f"Write a concise routing email (under 120 words) to {team} about IcM incident "
        f"{t.get('id')} ('{t.get('title','')}'). Summarize the issue and why it belongs to "
        f"them, and ask them to take ownership. Rationale: {cls['reasoning']}."
    )
    actions = [{"kind": "send_email", "target": email_to, "content": body}]
    return Command(goto=END, update={"proposed_actions": actions})


def build_app():
    g = StateGraph(TriageState)
    g.add_node("classify", classify)
    g.add_node("infra_branch", infra_branch)
    g.add_node("owner_branch", owner_branch)
    g.add_edge(START, "classify")
    g.add_edge("infra_branch", END)
    g.add_edge("owner_branch", END)
    return g.compile()
