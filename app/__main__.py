import asyncio
import fcntl
import logging
from logging.handlers import RotatingFileHandler
import os
import signal
import sys
from .config import ROOT,Config
from .gateway import Gateway

def main():
    if sys.prefix==sys.base_prefix:raise SystemExit('Use .venv/bin/python -m app')
    try:config=Config.load()
    except (ValueError,KeyError) as exc:raise SystemExit(str(exc))
    if not config.session.exists():
        raise SystemExit('Authorize the dedicated account first: .venv/bin/python -m scripts.authorize_telegram')
    os.umask(0o077)
    (ROOT/'data').mkdir(exist_ok=True,mode=0o700)
    (ROOT/'logs').mkdir(exist_ok=True,mode=0o700)
    handler=RotatingFileHandler(ROOT/'logs/little-k.log',maxBytes=2_000_000,backupCount=5)
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s'))
    logger=logging.getLogger();logger.setLevel(logging.INFO);logger.addHandler(handler)
    # Library logs can contain RPC or network diagnostics; application logs contain metadata only.
    for name in ('telethon','pytgcalls','httpx','httpcore'):logging.getLogger(name).setLevel(logging.ERROR)
    lock=(ROOT/'data/gateway.lock').open('w')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:raise SystemExit('A Little K gateway is already running')
    async def run():
        stop=asyncio.Event();loop=asyncio.get_running_loop()
        for sig in (signal.SIGTERM,signal.SIGINT):loop.add_signal_handler(sig,stop.set)
        logging.info('Service started Python=%s venv=%s',sys.version.split()[0],sys.prefix)
        gateway=Gateway(config)
        await gateway.run(stop)
    try:asyncio.run(run())
    except Exception as exc:logging.error('Service stopped type=%s',type(exc).__name__);raise SystemExit(1)
    finally:lock.close()

if __name__=='__main__':main()
