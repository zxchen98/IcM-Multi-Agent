"""
The whole triage policy lives here — edit THIS file to tune behavior.

  * INFRA_CRITERIA        what counts as "our team reboots it"
  * TEAMS                 the teams the LLM may route non-infra tickets to (+ their email)
  * TOOL_NAMES            map logical actions -> the exact tool names your MCP servers expose
  * GET_TICKETS_* / ...   how to pull the daily batch
"""

# ---------------------------------------------------------------------------
# Classification policy
# ---------------------------------------------------------------------------
INFRA_CRITERIA = (
    "An incident is 'infra_reboot' (OUR team's responsibility) when it is a server / "
    "infrastructure problem that is typically resolved by rebooting the affected server "
    "or node — e.g. host unresponsive, service down on a box, node stuck/hung, high "
    "memory/handle leak requiring restart, agent/daemon not responding. "
    "Everything else (application bugs, config, access, data, product-feature issues) is "
    "'route_to_team' and must be sent to the most appropriate team below."
)

# Teams the LLM can route non-infra tickets to. Keys are what the model picks.
TEAMS = {
    "pipeline_team":   {"description": "CI/CD pipelines, builds, deployments.",           "email": "pipeline-team@example.com"},
    "promptflow_team": {"description": "Prompt Flow, AI workflows, prompt engineering.",   "email": "promptflow-team@example.com"},
    "prs_team":        {"description": "Pull requests, code reviews, Git issues.",         "email": "prs-team@example.com"},
}

# Where anything not confidently matched to a team gets emailed.
FALLBACK_EMAIL = "icm-triage@example.com"

CLASSIFY_INSTRUCTIONS = (
    "You are the daily IcM triage classifier. For the given incident, decide whether it "
    "is an infra/server problem our team should fix by rebooting, or should be routed to "
    "another team. If routing, choose the single best team from the provided list."
)

# ---------------------------------------------------------------------------
# MCP wiring — set these to YOUR server's actual tool names (see startup log,
# which prints every loaded tool name).
# ---------------------------------------------------------------------------
TOOL_NAMES = {
    "get_tickets":     "get_tickets",       # returns the batch/queue of tickets
    "post_discussion": "post_discussion",   # posts a comment under a ticket
    "send_email":      "send_email",         # sends an email to a team/distro
    # "reboot_server":  <no MCP tool yet — stays a drafted/manual step>
}

# Arguments passed to the get_tickets tool (shape depends on your MCP server).
GET_TICKETS_ARGS: dict = {}   # e.g. {"query": "active infra", "limit": 50}

# ---------------------------------------------------------------------------
# Action mode: "propose" = draft only, human approves before execute phase.
# (Set by design decision; execute.py refuses to run un-approved decisions.)
# ---------------------------------------------------------------------------
ACTION_MODE = "propose"
