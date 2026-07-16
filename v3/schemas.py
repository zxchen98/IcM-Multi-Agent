"""Typed structures passed between graph nodes and written to the review file."""

from typing import TypedDict, Optional, List, Literal
from pydantic import BaseModel, Field


# ---- LangGraph state (what flows between nodes for ONE ticket) -------------
class TriageState(TypedDict):
    ticket: dict                 # {"id", "title", "text", "owning_team", ...}
    classification: dict         # filled by the classify node
    proposed_actions: list       # filled by the branch node


# ---- Structured outputs / persisted decision ------------------------------
class ProposedAction(BaseModel):
    kind: Literal["handle_infra", "send_email"]
    target: str = Field(..., description="server/incident to handle, or email recipient")
    content: str = Field("", description="drafted handling note or email body")


class TicketDecision(BaseModel):
    ticket_id: str
    title: str = ""
    category: str                        # infra | route_to_owner
    owning_team: Optional[str] = None    # set when category == route_to_owner
    reasoning: str = ""
    proposed_actions: List[ProposedAction] = []
    approved: bool = False               # <-- a human flips this to True in the review file
