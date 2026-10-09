import pytest
from app.config import Config

def test_portable_paths_and_key(tmp_path):
    cfg=Config.load()
    assert cfg.session==tmp_path/'little-k.session'
    assert cfg.db==tmp_path/'data/state.sqlite3'
    assert cfg.key_file==tmp_path/'hermes.env'
    assert cfg.key()=='fake-test-api-key'
    assert 'fake-test-hash' not in repr(cfg)

def test_default_profile_uses_renamed_little_k_companion(tmp_path):
    (tmp_path/'.env').write_text('''TELEGRAM_API_ID=12345
TELEGRAM_API_HASH=fake-test-hash
OWNER_USER_ID=1001
LITTLE_K_TELEGRAM_USER_ID=2002
''')
    cfg=Config.load()
    assert cfg.base_url=='http://127.0.0.1:8642/p/little-k-companion'
    assert cfg.key_file==__import__('pathlib').Path.home()/'.hermes/profiles/little-k-companion/.env'

def test_environment_overrides_and_home_expansion(monkeypatch):
    monkeypatch.setenv('HERMES_KEY_FILE','~/example/.env')
    monkeypatch.setenv('HERMES_API_KEY','override-secret')
    cfg=Config.load()
    assert cfg.key_file.is_absolute() and '~' not in str(cfg.key_file)
    assert cfg.key()=='override-secret'
    assert 'override-secret' not in repr(cfg)

def test_authorization_can_discover_identity(monkeypatch):
    monkeypatch.setenv('LITTLE_K_TELEGRAM_USER_ID','')
    assert Config.load(require_identity=False).identity==0
    with pytest.raises(ValueError):Config.load()

@pytest.mark.parametrize('url',['https://example.com','ftp://127.0.0.1','http://user:password@localhost'])
def test_nonlocal_or_invalid_hermes_url_rejected(monkeypatch,url):
    monkeypatch.setenv('HERMES_BASE_URL',url)
    with pytest.raises(ValueError):Config.load()

def test_missing_credentials_explained(tmp_path):
    (tmp_path/'.env').unlink()
    with pytest.raises(ValueError,match='configure .env'):Config.load()
