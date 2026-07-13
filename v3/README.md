# v3 — Daily IcM triage (LangGraph + MCP, human-approved)

Classifies each day's tickets and prepares the right action, with a human gate
before anything is sent.

```
Phase 1  python main.py triage
   get_tickets (MCP) ─▶ for each ticket:
        classify (LLM) ─▶ infra_reboot?  ── yes ─▶ draft reboot + discussion
                                          └─ no  ─▶ pick team, draft email + discussion
   ─▶ writes output/review.json  (+ review.md)

        ── human reviews, sets "approved": true ──

Phase 2  python main.py execute
   for each APPROVED decision ─▶ call MCP: send_email / post_discussion
                                 (reboot = manual: no MCP tool yet)
```

- **Data + actions come from your MCP servers** (`langchain-mcp-adapters`). The LLM only
  classifies and drafts text.
- **Routing is pure LLM** — `classify` picks `infra_reboot` vs `route_to_team` (and which
  team) via structured output; the graph branches on that (`Command(goto=...)`).
- **Propose, then approve** — Phase 1 never executes. Phase 2 runs only `approved` items.

## Files

| File | Role |
|---|---|
| `registry.py` | **Edit this.** Infra criteria, the team list (+ emails), your MCP tool names, batch query args. |
| `graph.py` | Per-ticket graph: `classify → infra_branch / route_branch`. |
| `batch.py` | Phase 1: fetch tickets, run graph, write `output/review.json`. |
| `execute.py` | Phase 2: perform approved `send_email` / `post_discussion` actions. |
| `mcp_tools.py` | Loads MCP tools; `call_tool(name, args)`. Only file touching MCP. |
| `schemas.py` | State + `TicketDecision` written to the review file. |
| `settings.py` / `llm.py` | Env + MCP config; Azure OpenAI model. |
| `config/mcp_servers.json` | Your MCP servers (stdio / streamable_http). |

## Setup

```bash
cd v3
pip install -r requirements.txt
cp .env.template .env                 # Azure OpenAI values
# 1) point config/mcp_servers.json at your MCP servers
# 2) in registry.py set TOOL_NAMES to your real tool names, and TEAMS + emails
python main.py one "Incident 123 : host westus-07 unresponsive, service down"   # quick test
python main.py triage
python main.py execute
```

## What you MUST adjust for your MCP servers

1. **`registry.py → TOOL_NAMES`** — the exact tool names your servers expose. The startup
   log prints every loaded tool name to copy from.
2. **`registry.py → GET_TICKETS_ARGS`** — args your `get_tickets` tool expects (query/limit).
3. **`batch.py → _normalize_ticket`** — map your ticket fields to `{id, title, text, server}`.
4. **`execute.py → _run_action`** — match the arg dicts (`to/subject/body`,
   `incident_id/comment`) to your `send_email` / `post_discussion` input schemas.

## Notes

- Everything is async; the CLI uses `asyncio.run`.
- Classification is one LLM call per ticket. If you need deeper investigation (pull logs
  before deciding), turn `classify` into a `create_react_agent` with your read tools and a
  `response_format` schema.
- Reboot: once you have a reboot MCP tool, add it to `TOOL_NAMES` and handle
  `reboot_server` in `execute.py` (currently a logged manual step).
- To make it a service instead of a CLI, wrap `triage_batch()` behind FastAPI like
  `v2-webapp`, or schedule `python main.py triage` on a cron.
