"""
icm_triage_server.py — LOCAL stdio MCP server that feeds the triage agent.

This is the one data source for the MVP. The LangGraph agent launches this file
as a subprocess (see config/mcp_servers.json) and calls its tools over stdio to
fetch tickets and the routing menu. The LLM does the classification; this server
only supplies data.

MVP data source = the historical ICM export (real tickets, fully offline). To go
live later, replace ONLY `_load_tickets()` with a call to the IcM API using the
running user's Entra ID (e.g. azure.identity.DefaultAzureCredential -> `az login`
token). Nothing else in the agent has to change.

Run standalone to sanity-check the data (no LLM, no MCP client needed):
    python servers/icm_triage_server.py --selftest

Inspect the tools in a browser:
    npx @modelcontextprotocol/inspector python servers/icm_triage_server.py
"""

import os
import sys
import json
import math
from pathlib import Path
from functools import lru_cache

import pandas as pd
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("icm-triage")

_V3_DIR = Path(__file__).resolve().parent.parent


def _default_data_path() -> Path:
    """Prefer a plaintext export inside v3/data (portable, not Purview-encrypted);
    fall back to the historical xlsx in v1-cli."""
    for name in ("tickets.json", "tickets.csv", "tickets.xlsx"):
        p = _V3_DIR / "data" / name
        if p.exists():
            return p
    return _V3_DIR.parent / "v1-cli" / "data" / "past_tickets_with_ai_summary.xlsx"


# Override with ICM_TICKETS_PATH. Supports .json / .csv / .xls / .xlsx.
DATA_PATH = Path(os.getenv("ICM_TICKETS_PATH", "") or _default_data_path())

# Columns the agent uses. AI_TransferredTo is the routing ground truth: it seeds
# the team menu (list_teams) and lets you score the agent, so it is NOT shown to
# the classifier as ticket content (batch.py strips it before prompting).
_FIELDS = [
    "IncidentId", "Title", "Severity", "Product", "ticket_category",
    "OwningTeamName", "Summary", "Investigation",
    "AI_ProblemStage", "AI_KeyLog", "AI_Conclusion", "AI_Solution",
    "AI_TransferredTo",
]
LABEL_FIELD = "AI_TransferredTo"


# --------------------------------------------------------------------------- data
def _read_frame(path: Path) -> pd.DataFrame:
    """Load tickets from .json / .csv / .xls / .xlsx into a DataFrame."""
    suffix = path.suffix.lower()
    if suffix == ".json":
        return pd.read_json(path)
    if suffix == ".csv":
        return pd.read_csv(path)
    # Excel: the export is sometimes an old OLE .xls despite the .xlsx name, and a
    # Purview/RMS sensitivity label can encrypt it (unreadable without decrypting
    # under your Entra ID). Try both engines and give a clear hint if it's sealed.
    errors = []
    for engine in ("openpyxl", "xlrd"):
        try:
            return pd.read_excel(path, engine=engine)
        except Exception as e:  # BadZipFile, ImportError, ValueError, ...
            errors.append(f"{engine}: {e}")
    raise RuntimeError(
        f"Could not read {path}. If it's Purview-encrypted, export a plaintext "
        f"copy to v3/data/tickets.json (or set ICM_TICKETS_PATH). Details: {errors}"
    )


@lru_cache(maxsize=1)
def _load_tickets() -> list[dict]:
    """
    THE SEAM. Returns the ticket universe as plain dicts.

    MVP: read the historical export. To use live IcM, swap the body of this
    function for an IcM API call authenticated with the user's Entra ID token —
    keep the same {field: value} shape and the rest of the server is unchanged.
    """
    if not DATA_PATH.exists():
        raise FileNotFoundError(
            f"Ticket data not found at {DATA_PATH}. "
            f"Set ICM_TICKETS_PATH to the historical export."
        )
    df = _read_frame(DATA_PATH)
    keep = [c for c in _FIELDS if c in df.columns]
    records = df[keep].to_dict(orient="records")
    return [_clean(r) for r in records]


def _clean(row: dict) -> dict:
    """Drop NaN/NaT so the result is JSON-serializable and the LLM sees clean text."""
    out = {}
    for k, v in row.items():
        if isinstance(v, float) and math.isnan(v):
            continue
        if v is None or (isinstance(v, str) and not v.strip()):
            continue
        out[k] = str(v).strip() if not isinstance(v, (int, float, bool)) else v
    return out


def _is_routed(ticket: dict) -> bool:
    return bool(ticket.get("AI_TransferredTo"))


# --------------------------------------------------------------------------- tools
@mcp.tool()
def get_tickets(limit: int = 20, unrouted_only: bool = False) -> list[dict]:
    """Return a batch of ICM tickets to triage.

    Args:
        limit: max number of tickets to return.
        unrouted_only: if true, only tickets that don't yet have a team assigned
            (AI_TransferredTo empty) — i.e. the ones that still need routing.

    Each ticket includes IncidentId, Title, Product, Investigation and the AI_*
    summary fields. Use these to decide which team should own the incident.
    """
    tickets = _load_tickets()
    if unrouted_only:
        tickets = [t for t in tickets if not _is_routed(t)]
    return tickets[: max(0, limit)]


@mcp.tool()
def get_ticket(incident_id: str) -> dict:
    """Return the full detail for a single ICM ticket by its IncidentId.

    Returns an empty dict if no ticket matches.
    """
    for t in _load_tickets():
        if str(t.get("IncidentId", "")) == str(incident_id):
            return t
    return {}


@mcp.tool()
def list_teams() -> list[dict]:
    """Return the routing menu: the distinct teams tickets have historically been
    transferred to (from AI_TransferredTo), with how many tickets each has owned.

    Use this as the set of valid routing targets — route each ticket to one of
    these teams. Sorted by frequency (most common owner first).
    """
    counts: dict[str, int] = {}
    for t in _load_tickets():
        team = t.get("AI_TransferredTo")
        if team:
            counts[team] = counts.get(team, 0) + 1
    return [
        {"team": team, "ticket_count": n}
        for team, n in sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    ]


# --------------------------------------------------------------------------- entry
def _selftest() -> None:
    tickets = _load_tickets()
    teams = list_teams()
    print(f"[ok] Loaded {len(tickets)} tickets from {DATA_PATH}")
    print(f"[ok] {len(teams)} distinct routing targets (top 10):")
    for row in teams[:10]:
        print(f"     {row['ticket_count']:>4}  {row['team']}")
    if tickets:
        print("\nSample ticket:")
        for k, v in list(tickets[0].items()):
            print(f"     {k}: {str(v)[:100]}")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        mcp.run()  # stdio: the agent launches this file and talks over stdin/stdout
