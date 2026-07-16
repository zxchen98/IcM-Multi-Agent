# v3 — Daily IcM triage MVP (LangGraph + local MCP)

Binary triage: for each ticket, decide **infra** (our team fixes it) vs
**route_to_owner** (email the owning team), and draft the matching action. Runs
locally under your own Entra ID — no service principal.

```
python main.py triage
   get_tickets (local MCP) ─▶ for each ticket:
        classify (LLM, binary) ─▶ infra?  ── yes ─▶ draft infra handling note
                                          └─ no  ─▶ draft email to owning team
   ─▶ writes output/review.json  (+ review.md)

        ── human reviews, sets "approved": true ──

python main.py execute      # MVP: report-only. Prints approved drafts to send by hand.
```

- **Tickets come from one local stdio MCP server** (`servers/icm_triage_server.py`),
  not from the cloud servers your coworker used. The LLM only classifies and drafts text.
- **Propose, then approve** — triage never sends anything. There is no mail tool wired
  in the MVP, so route emails are drafted for a human to send.

## Files

| File | Role |
|---|---|
| `servers/icm_triage_server.py` | **The data source.** Local stdio MCP: `get_tickets`, `get_ticket`, `list_teams`. Reads `data/tickets.json`. |
| `registry.py` | **Edit this.** `INFRA_CRITERIA` (what our team fixes), `OWNER_EMAILS`, `FALLBACK_EMAIL`, tool names. |
| `graph.py` | Per-ticket graph: `classify → infra_branch / owner_branch`. |
| `batch.py` | Phase 1: fetch tickets, run graph, write `output/review.json`. |
| `execute.py` | Phase 2 (MVP): print approved drafts to send/perform manually. |
| `mcp_tools.py` | Loads MCP tools; `call_tool(name, args)`. Only file touching MCP. |
| `schemas.py` / `settings.py` / `llm.py` | State/decision types; env + MCP config; Azure OpenAI model. |
| `config/mcp_servers.json` | Points at the local `icm-triage` stdio server. |
| `data/tickets.json` | Plaintext ticket export the server reads (see note below). |

## Setup

```bash
cd v3
python -m venv .venv && .venv\Scripts\activate      # use a clean venv
pip install -r requirements.txt
copy .env.template .env                              # fill in Azure OpenAI values

python servers/icm_triage_server.py --selftest       # verify data loads (no LLM)
python main.py one "host westus-07 unresponsive, service down"   # single-ticket test
python main.py triage                                # batch -> output/review.json
python main.py execute                               # print approved drafts
```

## What you adjust

1. **`registry.py → INFRA_CRITERIA`** — the definition of "our team fixes it" for YOUR charter.
2. **`registry.py → OWNER_EMAILS` / `FALLBACK_EMAIL`** — where route emails are addressed.
3. **`data/tickets.json`** — the tickets to triage (fields: `IncidentId, Title, Severity,
   Product, ticket_category, OwningTeamName, Summary, Investigation, AI_*`).

## Data note (Purview encryption)

The historical export `v1-cli/data/past_tickets_with_ai_summary.xlsx` gets **encrypted by
a Purview/RMS sensitivity label** in the working tree (unreadable by pandas without
decrypting under your Entra ID). `data/tickets.json` was derived from the *committed,
unencrypted* copy so the MVP runs offline. To go live, replace `_load_tickets()` in
`servers/icm_triage_server.py` with an IcM API call authenticated by your Entra ID —
nothing else changes.

## Next steps (post-MVP)

- Wire a mail path (Graph API / a mail MCP) so `execute.py` actually sends the route emails.
- Swap the server's `_load_tickets()` seam from `tickets.json` to live IcM (your Entra ID).
- Score classifications against the held-out `AI_TransferredTo` label to tune `INFRA_CRITERIA`.
