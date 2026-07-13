"""Typed structures passed between graph nodes and written to the review file."""

from typing import TypedDict, Optional, List, Literal
from pydantic import BaseModel, Field


# ---- LangGraph state (what flows between nodes for ONE ticket) -------------
class TriageState(TypedDict):
    ticket: dict                 # {"id", "title", "text", ...} from the get-tickets MCP
    classification: dict         # filled by the classify node
    proposed_actions: list       # filled by the branch node


# ---- Structured outputs / persisted decision ------------------------------
class ProposedAction(BaseModel):
    kind: Literal["reboot_server", "send_email", "post_discussion"]
    target: str = Field(..., description="server name / email recipient / ticket id")
    content: str = Field("", description="drafted body: reboot rationale, email text, or discussion text")


class TicketDecision(BaseModel):
    ticket_id: str
    title: str = ""
    category: str                        # infra_reboot | route_to_team
    target_team: Optional[str] = None    # set when category == route_to_team
    reasoning: str = ""
    proposed_actions: List[ProposedAction] = []
    approved: bool = False               # <-- a human flips this to True in the review file
