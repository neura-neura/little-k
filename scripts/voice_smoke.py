"""Explicit local test: never creates a Telegram call; group must be allowlisted."""
import asyncio
import json
import sys
from app.diagnostics import query
async def main():
    if len(sys.argv)!=3:raise SystemExit('Usage: .venv/bin/python -m scripts.voice_smoke GROUP_ID LANGUAGE')
    print(json.dumps(await query('voice_smoke',chat=int(sys.argv[1]),language=sys.argv[2])))
if __name__=='__main__':asyncio.run(main())
