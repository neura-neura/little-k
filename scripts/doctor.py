import asyncio
import fcntl
import importlib
import json
import shutil
import subprocess
import sys
from telethon import TelegramClient
from app.config import Config,ROOT
from app.hermes import Hermes
from app.storage import Storage
from app.tts import TTS
from scripts.service import LABEL,DOMAIN,PLIST

async def main():
    (ROOT/'data').mkdir(exist_ok=True,mode=0o700)
    results={}
    def result(name,ok,detail=''):
        results[name]={'ok':bool(ok),'detail':detail};print(f'{name}: {"OK" if ok else "FAIL"} {detail}')
    result('Python venv',sys.prefix!=sys.base_prefix,sys.version.split()[0])
    cfg=Config.load()
    if not cfg.session.exists():
        result('Telegram session',False,'Run .venv/bin/python -m scripts.authorize_telegram first')
        return 1
    for module in ['telethon','pytgcalls','ntgcalls','httpx','dotenv','yaml']:
        try:importlib.import_module(module);result('Dependency '+module,True)
        except Exception as exc:result('Dependency '+module,False,type(exc).__name__)
    result('OWNER config',cfg.owner!=cfg.identity,'distinct identities')
    result('Telegram session',cfg.session.exists() and (cfg.session.stat().st_mode&0o077)==0,'restricted permissions')
    # Never concurrently open the production SQLite session while the gateway owns it.
    service_state=subprocess.run(['/bin/launchctl','print',DOMAIN+'/'+LABEL],capture_output=True,text=True)
    service_loaded=service_state.returncode==0
    lock=(ROOT/'data/gateway.lock').open('a')
    try:
        if service_loaded:running=True
        else:
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);running=False
            except BlockingIOError:running=True
        if running:
            try:
                from app.diagnostics import query
                status=await query()
                result('Telegram connection',status.get('telegram_connected',False),'live private diagnostic socket')
                result('Little K Telegram account',status.get('identity_verified',False) and status.get('identity')==cfg.identity)
                result('Voice library',status.get('voice_library_started',False),'native library initialized')
            except Exception as exc:result('Telegram connection',False,type(exc).__name__)
        else:
            c=TelegramClient(str(cfg.session),cfg.api_id,cfg.api_hash)
            try:
                await c.connect();result('Telegram connection',c.is_connected())
                me=await c.get_me();result('Little K Telegram account',me is not None and me.id==cfg.identity and me.id!=cfg.owner and not me.bot)
            except Exception as exc:result('Telegram connection',False,type(exc).__name__)
            finally:await c.disconnect()
    finally:lock.close()
    h=Hermes(cfg)
    try:
        await h.health();await h.request('GET','/v1/toolsets');result('Hermes',True)
        result('Little K Hermes bot',True,'authenticated native profile route')
    except Exception as exc:result('Hermes',False,type(exc).__name__)
    finally:await h.close()
    try:
        s=Storage(cfg.db,recover=False);integrity=s.db.execute('PRAGMA integrity_check').fetchone()[0];s.close();result('Database',integrity=='ok')
    except Exception as exc:result('Database',False,type(exc).__name__)
    result('ffmpeg',bool(shutil.which(cfg.ffmpeg)))
    tts=TTS(cfg)
    for language,text in [('es','Hola, soy Little K.'),('en','Hello, I am Little K.'),('zh','你好，我是小猫。'),('ja','こんにちは。')]:
        try:path=await tts.synthesize(text,language);result('TTS '+language,True,cfg.voices[language]);tts.cleanup(path)
        except Exception as exc:result('TTS '+language,False,type(exc).__name__)
    r=subprocess.run(['/bin/launchctl','print',DOMAIN+'/'+LABEL],capture_output=True,text=True)
    if '--skip-service' not in sys.argv:
        result('launchd',r.returncode==0 and 'state = running' in r.stdout,str(PLIST))
    (ROOT/'data/doctor.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
    return 0 if all(x['ok'] for x in results.values()) else 1
if __name__=='__main__':raise SystemExit(asyncio.run(main()))
