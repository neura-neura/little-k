"""All tests use fictitious credentials; no installed Telegram or Hermes account needed."""
import pytest
from app import config

@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'ROOT', tmp_path)
    for key in list(__import__('os').environ):
        if key.startswith(('TELEGRAM_', 'HERMES_', 'VOICE_', 'LITTLE_K_')) or key in (
            'OWNER_USER_ID','ALLOWED_CHAT_IDS','ALLOWED_PRIVATE_USER_IDS','DATABASE_PATH','FFMPEG_PATH','TTS_RATE'):
            monkeypatch.delenv(key)
    (tmp_path/'.env').write_text('''TELEGRAM_API_ID=12345
TELEGRAM_API_HASH=fake-test-hash
OWNER_USER_ID=1001
LITTLE_K_TELEGRAM_USER_ID=2002
ALLOWED_CHAT_IDS=-1003003
HERMES_BASE_URL=http://127.0.0.1:8642/p/little-k
HERMES_KEY_FILE=hermes.env
''')
    (tmp_path/'hermes.env').write_text('API_SERVER_KEY=fake-test-api-key\n')
