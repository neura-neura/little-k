"""Provision a native Hermes profile without embedding model/provider credentials."""
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
from urllib.parse import urlparse
from dotenv import dotenv_values, set_key
from app.config import ROOT


def ensure_key(path):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not dotenv_values(path).get('API_SERVER_KEY'):
        set_key(str(path), 'API_SERVER_KEY', secrets.token_urlsafe(32))
    path.chmod(0o600)


def main():
    os.umask(0o077)
    settings=dotenv_values(ROOT/'.env')
    profile=os.environ.get('HERMES_PROFILE') or settings.get('HERMES_PROFILE') or 'little-k-companion'
    if not re.fullmatch(r'[a-z][a-z0-9-]{0,63}',profile) or profile=='default':
        raise SystemExit('Use a separate Hermes profile name, such as little-k-companion.')
    home=Path(os.environ.get('HERMES_HOME','~/.hermes')).expanduser()
    if not (home/'config.yaml').exists():
        raise SystemExit('Install Hermes and configure its default model/provider first; see README.')
    cli=os.environ.get('HERMES_CLI') or shutil.which('hermes')
    if not cli:raise SystemExit('hermes CLI not found on PATH; install Hermes first.')
    def command(*args):
        # Capture native output: some setup diagnostics may include credentials.
        result=subprocess.run([cli,'--profile','default',*args],capture_output=True,text=True)
        if result.returncode:raise SystemExit('Hermes command failed: '+ ' '.join(args)+'. Run it directly to diagnose.')
    directory=home/'profiles'/profile
    if not directory.exists():
        command('profile','create',profile,'--clone-from','default','--no-alias')
        (directory/'SOUL.md').write_text((ROOT/'config/SOUL.md').read_text(),encoding='utf-8')
    if not (directory/'config.yaml').exists():
        raise SystemExit('Hermes profile creation incomplete; check the native Hermes installation.')
    ensure_key(directory/'.env')
    root_env=home/'.env'
    existing=dotenv_values(root_env)
    url=os.environ.get('HERMES_BASE_URL') or settings.get('HERMES_BASE_URL') or f'http://127.0.0.1:8642/p/{profile}'
    parsed=urlparse(url)
    if parsed.scheme!='http' or parsed.hostname not in ('127.0.0.1','localhost','::1') or parsed.path.rstrip('/')!=f'/p/{profile}' or parsed.username:
        raise SystemExit('Setup expects a loopback HTTP URL ending in /p/'+profile)
    port=parsed.port or 80
    if existing.get('API_SERVER_HOST','127.0.0.1') not in ('127.0.0.1','localhost','::1'):
        raise SystemExit('Existing Hermes API bind address is not loopback; configure Hermes before continuing.')
    if existing.get('API_SERVER_PORT') and int(existing['API_SERVER_PORT'])!=port:
        raise SystemExit('HERMES_BASE_URL must match the existing Hermes API_SERVER_PORT.')
    (ROOT/'data').mkdir(exist_ok=True,mode=0o700)
    backup=ROOT/'data/hermes-env.before-setup'
    if root_env.exists() and not backup.exists():
        shutil.copyfile(root_env,backup);backup.chmod(0o600)
    ensure_key(root_env)
    if not existing.get('API_SERVER_HOST'):set_key(str(root_env),'API_SERVER_HOST','127.0.0.1')
    if not existing.get('API_SERVER_PORT'):set_key(str(root_env),'API_SERVER_PORT',str(port))
    command('config','set','gateway.multiplex_profiles','true')
    set_key(str(ROOT/'.env'),'HERMES_KEY_FILE',str(directory/'.env'))
    (ROOT/'.env').chmod(0o600)
    print('Hermes profile ready. Existing profile personality and model settings preserved.')
    print('Restart the native listener: hermes --profile default gateway restart')
    print('If no native service is installed, run: hermes --profile default gateway run')

if __name__=='__main__':main()
