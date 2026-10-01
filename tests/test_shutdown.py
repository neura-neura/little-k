"""Exercise real native destructors in a separate process, with no Telegram login."""
import subprocess
import sys
from pathlib import Path
import pytest

@pytest.mark.parametrize('with_callbacks',[False,True])
def test_native_voice_shutdown_exits_cleanly(tmp_path,with_callbacks):
    code='''
import asyncio
from dataclasses import replace
from pathlib import Path
from telethon import TelegramClient
from app.config import Config
from app.storage import Storage
from app.voice import Voice
from unittest.mock import AsyncMock

async def main():
    cfg=Config.load(root=Path(__import__('sys').argv[1]))
    storage=Storage(cfg.db)
    client=TelegramClient(str(cfg.session),cfg.api_id,cfg.api_hash)
    voice=Voice(client,cfg,storage,AsyncMock())
    if __import__('sys').argv[2]=='True':
        # Same native/Python ownership cycle installed by PyTgCalls.start().
        voice.calls._binding.on_stream_end(lambda *args: voice.calls.loop)
        voice.calls._binding.on_upgrade(lambda *args: voice.calls.loop)
    await voice.close()
    await voice.close()  # shutdown is idempotent
    assert voice.calls._binding is None
    assert voice.calls.executor._shutdown
    await client.disconnect()
    storage.close()

asyncio.run(main())
'''
    result=subprocess.run([sys.executable,'-c',code,str(tmp_path),str(with_callbacks)],
                          cwd=Path(__file__).resolve().parent.parent,capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stderr
