import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent

def ids(value):
    return frozenset(int(x.strip()) for x in (value or '').split(',') if x.strip())

@dataclass(frozen=True)
class Config:
    api_id: int
    api_hash: str = field(repr=False)
    owner: int
    identity: int
    chats: frozenset
    private_users: frozenset
    session: Path
    base_url: str
    key_file: Path
    timeout: float
    voice_enabled: bool
    idle_timeout: float
    rate: int
    voices: dict
    ffmpeg: str
    db: Path
    api_key: str = field(default="", repr=False)

    @classmethod
    def load(cls, root=None, require_identity=True):
        root = Path(root) if root is not None else ROOT
        d = {}
        for name in ('little-k_api-id_api-hash.env', 'little-k_allowed-ids.env', '.env'):
            d.update({k:v for k,v in dotenv_values(root/name).items() if v is not None})
        supported = set(d) | {'TELEGRAM_API_ID','TELEGRAM_API_HASH','OWNER_USER_ID',
            'LITTLE_K_TELEGRAM_USER_ID','ALLOWED_CHAT_IDS','ALLOWED_PRIVATE_USER_IDS',
            'TELEGRAM_SESSION_PATH','HERMES_BASE_URL','HERMES_KEY_FILE','HERMES_API_KEY',
            'HERMES_PROFILE','HERMES_TIMEOUT','VOICE_ENABLED','VOICE_IDLE_TIMEOUT',
            'TTS_RATE','FFMPEG_PATH','DATABASE_PATH'} | {'VOICE_'+x for x in ('ES','EN','ZH','JA','KO','FR','DE','PT','IT')}
        d.update({k:os.environ[k] for k in supported if k in os.environ})
        for key in ('TELEGRAM_API_ID','TELEGRAM_API_HASH','OWNER_USER_ID'):
            if not d.get(key):raise ValueError(f'Missing {key}; configure .env from .env.example')
        owner, identity = int(d['OWNER_USER_ID']), int(d.get('LITTLE_K_TELEGRAM_USER_ID') or 0)
        if owner <= 0 or int(d['TELEGRAM_API_ID']) <= 0 or (require_identity and identity <= 0):
            raise ValueError('Positive account IDs required; run scripts.authorize_telegram first')
        def path(value):
            p=Path(value).expanduser()
            return p if p.is_absolute() else root/p
        if owner == identity:
            raise ValueError('OWNER must differ from Little K identity')
        url = d.get('HERMES_BASE_URL','http://127.0.0.1:8642/p/little-k').rstrip('/')
        if urlparse(url).scheme not in ('http','https') or urlparse(url).username or urlparse(url).hostname not in ('127.0.0.1', 'localhost', '::1'):
            raise ValueError('Hermes URL must be local loopback')
        if d.get('VOICE_ENABLED','true').lower() not in ('true','false'):
            raise ValueError('VOICE_ENABLED must be true or false')
        for key, default in (('HERMES_TIMEOUT',240),('VOICE_IDLE_TIMEOUT',20),('TTS_RATE',185)):
            if float(d.get(key,default)) <= 0:
                raise ValueError(f'{key} must be positive')
        return cls(int(d['TELEGRAM_API_ID']), d['TELEGRAM_API_HASH'], owner, identity,
                   ids(d.get('ALLOWED_CHAT_IDS')), ids(d.get('ALLOWED_PRIVATE_USER_IDS')),
                   path(d.get('TELEGRAM_SESSION_PATH') or 'little-k.session'), url,
                   path(d.get('HERMES_KEY_FILE') or f"~/.hermes/profiles/{d.get('HERMES_PROFILE','little-k')}/.env"), float(d.get('HERMES_TIMEOUT',240)),
                   d.get('VOICE_ENABLED','true').lower()=='true', float(d.get('VOICE_IDLE_TIMEOUT',20)),
                   int(d.get('TTS_RATE',185)),
                   {lang:d.get('VOICE_'+lang.upper(), voice) for lang,voice in
                    {'es':'Paulina','en':'Samantha','zh':'Tingting','ja':'Kyoko','ko':'Yuna',
                     'fr':'Thomas','de':'Anna','pt':'Luciana','it':'Alice'}.items()},
                   d.get('FFMPEG_PATH') or shutil.which('ffmpeg') or 'ffmpeg',
                   path(d.get('DATABASE_PATH') or 'data/state.sqlite3'), d.get('HERMES_API_KEY',''))

    def allowed(self, chat, sender, private, outgoing=False):
        if outgoing or sender == self.identity or sender is None:
            return False
        if private:
            return sender == self.owner or sender in self.private_users
        return chat in self.chats

    def key(self):
        key = self.api_key or dotenv_values(self.key_file).get('API_SERVER_KEY')
        if not key:
            raise ValueError('Hermes profile API key missing')
        return key
