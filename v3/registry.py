"""
The whole triage policy lives here — edit THIS file to tune behavior.

MVP decision is BINARY:
  * infra           -> OUR team owns/fixes it (e.g. reboot the box, on-call action)
  * route_to_owner  -> someone else's problem -> draft an email to the owning team

  * INFRA_CRITERIA   what counts as "our team fixes it"
  * OWNER_EMAILS     optional team-name -> email map for the route_to_owner branch
  * FALLBACK_EMAIL   where a route email goes when the team isn't in OWNER_EMAILS
  * TOOL_NAMES       the exact tool names the icm-triage MCP server exposes
  * GET_TICKETS_ARGS args passed to the get_tickets tool
"""

# ---------------------------------------------------------------------------
# Classification policy  (edit INFRA_CRITERIA to match YOUR team's charter)
# ---------------------------------------------------------------------------
OUR_TEAM = "our infra/on-call team"

INFRA_CRITERIA = (
    "An incident is 'infra' (OUR team fixes it) when it is a server / node / "
    "host / hardware / capacity problem that our on-call resolves directly — "
    "e.g. host unresponsive, node stuck/hung, service down on a box, agent/daemon "
    "not responding, disk/memory pressure or a machine needing a reboot. "
    "Everything else — application bugs, job/pipeline logic, config, access, data, "
    "product-feature issues — is 'route_to_owner': it belongs to the team that owns "
    "that product/area, and we email them."
)

CLASSIFY_INSTRUCTIONS = (
    f"You are the daily IcM triage classifier for {OUR_TEAM}. For the given "
    "incident, decide whether OUR team fixes it (infra) or it should be routed to "
    "its owning team (route_to_owner). When routing, name the owning team as "
    "precisely as the incident allows (use the incident's own owning-team / product "
    "signals)."
)

# Optional: map an owning-team name to a real email. Unknown teams fall back below.
# Keys are matched case-insensitively against the team the model names.
OWNER_EMAILS: dict[str, str] = {
    # "Project Vienna Services/AEther": "aether-owners@example.com",
}

# Where a route_to_owner email goes when the owning team isn't in OWNER_EMAILS.
FALLBACK_EMAIL = "icm-triage@example.com"

# ---------------------------------------------------------------------------
# MCP wiring — tool names exposed by servers/icm_triage_server.py
# ---------------------------------------------------------------------------
TOOL_NAMES = {
    "get_tickets": "get_tickets",   # returns the batch of tickets to triage
    "get_ticket":  "get_ticket",    # single ticket by IncidentId
    "list_teams":  "list_teams",    # historical routing targets (context only)
}

# Arguments passed to get_tickets (see the tool's signature).
GET_TICKETS_ARGS: dict = {"limit": 20}

# Action mode: "propose" = draft only; nothing is sent. (No mail tool is wired in
# the MVP, so route emails are drafted for a human to review/send.)
ACTION_MODE = "propose"
