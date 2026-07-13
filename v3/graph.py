"""
Per-ticket triage graph (the LLM-decided branch you liked):

    START -> classify ─▶ infra_reboot?  ── yes ─▶ infra_branch  -> END
                                          └─ no  ─▶ route_branch -> END

`classify` is one structured-output LLM call. Each branch DRAFTS the actions
(propose mode) — nothing is executed here. batch.py runs many tickets through
this graph; execute.py performs the approved actions later.
"""

from typing import Optional, Literal
from pydantic import create_model, Field
from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, START, END
from langgraph.types import Command

from llm import get_model
from schemas import TriageState
from registry import (
    INFRA_CRITERIA, CLASSIFY_INSTRUCTIONS, TEAMS, FALLBACK_EMAIL,
)


def _ticket_text(ticket: dict) -> str:
    return (
        f"Incident ID: {ticket.get('id', '?')}\n"
        f"Title: {ticket.get('title', '')}\n"
        f"Details:\n{ticket.get('text', '')}"
    )


def _classification_model():
    """LLM must return a valid category and (if routing) a valid team key."""
    team_keys = tuple(TEAMS.keys())
    return create_model(
        "Classification",
        category=(Literal["infra_reboot", "route_to_team"],
                  Field(..., description="infra_reboot = our team reboots; route_to_team = hand off")),
        target_team=(Optional[Literal[team_keys]],
                     Field(None, description="team to route to when category==route_to_team, else null")),
        reasoning=(str, Field(..., description="one-sentence justification")),
    )


async def _draft(instruction: str) -> str:
    """Small helper to draft a discussion/email body with the LLM."""
    resp = await get_model().ainvoke([HumanMessage(content=instruction)])
    return resp.content.strip()


# --------------------------------------------------------------------------- nodes
async def classify(state: TriageState):
    ticket = state["ticket"]
    Model = _classification_model()
    team_menu = "\n".join(f"  - {k}: {v['description']}" for k, v in TEAMS.items())
    prompt = (
        f"{CLASSIFY_INSTRUCTIONS}\n\n{INFRA_CRITERIA}\n\n"
        f"Teams you may route to:\n{team_menu}\n\n"
        f"Incident:\n{_ticket_text(ticket)}"
    )
    result = await get_model().with_structured_output(Model).ainvoke([HumanMessage(content=prompt)])
    cls = result.model_dump()
    goto = "infra_branch" if cls["category"] == "infra_reboot" else "route_branch"
    print(f"🧭 {ticket.get('id','?')} → {cls['category']}"
          f"{'/' + str(cls['target_team']) if cls['target_team'] else ''}: {cls['reasoning']}")
    return Command(goto=goto, update={"classification": cls})


async def infra_branch(state: TriageState):
    """Our team's server/infra issue → draft reboot + a discussion comment."""
    t, cls = state["ticket"], state["classification"]
    server = t.get("server") or t.get("occurring_device") or "<server-from-ticket>"
    discussion = await _draft(
        f"Write a short IcM discussion comment for incident {t.get('id')} "
        f"('{t.get('title','')}'). State that this is a server/infra issue owned by our team, "
        f"that a reboot of {server} is the planned remediation, and that we are handling it. "
        f"Rationale: {cls['reasoning']}. Keep it professional and under 100 words."
    )
    actions = [
        {"kind": "reboot_server", "target": server,
         "content": f"Reboot {server}. Rationale: {cls['reasoning']} "
                    f"(no reboot MCP tool wired yet — manual/approval step)."},
        {"kind": "post_discussion", "target": str(t.get("id", "")), "content": discussion},
    ]
    return Command(goto=END, update={"proposed_actions": actions})


async def route_branch(state: TriageState):
    """Not ours → draft an email to the chosen team + a discussion comment."""
    t, cls = state["ticket"], state["classification"]
    team_key = cls.get("target_team")
    team = TEAMS.get(team_key)
    email_to = team["email"] if team else FALLBACK_EMAIL
    email_body = await _draft(
        f"Write a concise routing email to the {team_key or 'triage'} team about IcM incident "
        f"{t.get('id')} ('{t.get('title','')}'). Summarize the issue and why it belongs to them. "
        f"Rationale: {cls['reasoning']}. Under 120 words."
    )
    discussion = await _draft(
        f"Write a short IcM discussion comment for incident {t.get('id')} stating it has been "
        f"triaged and routed to the {team_key or 'triage'} team, with a one-line reason."
    )
    actions = [
        {"kind": "send_email", "target": email_to, "content": email_body},
        {"kind": "post_discussion", "target": str(t.get("id", "")), "content": discussion},
    ]
    return Command(goto=END, update={"proposed_actions": actions})


def build_app():
    """Compile the per-ticket triage graph (no MCP tools needed at classify time)."""
    g = StateGraph(TriageState)
    g.add_node("classify", classify)
    g.add_node("infra_branch", infra_branch)
    g.add_node("route_branch", route_branch)
    g.add_edge(START, "classify")
    g.add_edge("infra_branch", END)
    g.add_edge("route_branch", END)
    return g.compile()
