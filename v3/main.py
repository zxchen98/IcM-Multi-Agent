"""
v3 CLI — local-MCP daily IcM triage (binary: infra vs route_to_owner) with a
human-approval gate.

    python main.py triage     # Phase 1: fetch batch, classify, draft -> output/review.json
    # ... open output/review.json, set "approved": true on the ones to keep ...
    python main.py execute    # Phase 2 (MVP): print approved drafts to send/perform by hand

Single-ticket test (no MCP fetch needed):
    python main.py one "<incident text or id>"
"""

import sys
import asyncio

from settings import check_env


async def _triage():
    from batch import triage_batch
    await triage_batch()


async def _execute():
    from execute import execute_reviewed
    await execute_reviewed()


async def _one(text: str):
    from graph import build_app
    app = build_app()
    final = await app.ainvoke({"ticket": {"id": text[:20], "title": "", "text": text}})
    print("\nClassification:", final["classification"])
    print("Proposed actions:")
    for a in final["proposed_actions"]:
        print(f"  - {a['kind']} → {a['target']}\n      {a['content']}")


def main():
    missing = check_env()
    if missing:
        print(f"❌ Missing env vars: {', '.join(missing)}  (copy .env.template to .env)")
        return

    cmd = sys.argv[1] if len(sys.argv) > 1 else "triage"
    if cmd == "triage":
        asyncio.run(_triage())
    elif cmd == "execute":
        asyncio.run(_execute())
    elif cmd == "one":
        asyncio.run(_one(" ".join(sys.argv[2:]) or "test incident"))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
