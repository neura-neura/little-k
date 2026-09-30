"""Run interactively with .venv/bin/python -m scripts.authorize_telegram."""
import asyncio
import getpass
import os
import fcntl
from dotenv import set_key
import sys
from telethon import TelegramClient, errors
from app.config import Config, ROOT

async def main():
    if sys.prefix==sys.base_prefix:raise SystemExit('Use the project venv')
    os.umask(0o077)
    (ROOT/'data').mkdir(exist_ok=True,mode=0o700)
    lock=(ROOT/'data/gateway.lock').open('a')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:raise SystemExit('Stop Little K before authorizing Telegram.')
    config=Config.load(require_identity=False)
    config.session.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    c=TelegramClient(str(config.session),config.api_id,config.api_hash)
    await c.connect()
    try:
        if not await c.is_user_authorized():
            phone=input('Dedicated Little K phone (+country code): ').strip()
            await c.send_code_request(phone)
            try:await c.sign_in(phone=phone,code=getpass.getpass('Telegram code: '))
            except errors.SessionPasswordNeededError:await c.sign_in(password=getpass.getpass('Little K 2FA password: '))
        me=await c.get_me()
        if (config.identity and me.id!=config.identity) or me.id==config.owner or me.bot:
            raise SystemExit('Wrong account. Stop: authorize only the dedicated Little K account.')
        if not config.identity:
            set_key(str(ROOT/'.env'),'LITTLE_K_TELEGRAM_USER_ID',str(me.id));(ROOT/'.env').chmod(0o600)
        config.session.chmod(0o600);print('Dedicated Little K identity verified; session ready.')
    finally:
        await c.disconnect()
        lock.close()
if __name__=='__main__':asyncio.run(main())
