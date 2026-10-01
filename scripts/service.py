import os
import plistlib
import subprocess
import sys
import time
from pathlib import Path
from app.config import ROOT
from dotenv import dotenv_values
LABEL=os.environ.get('LITTLE_K_SERVICE_LABEL') or dotenv_values(ROOT/'.env').get('LITTLE_K_SERVICE_LABEL') or 'io.github.little-k.gateway'
PLIST=Path.home()/'Library/LaunchAgents'/f'{LABEL}.plist'
DOMAIN=f'gui/{os.getuid()}'

def command(*args,check=True):
    return subprocess.run(['/bin/launchctl',*args],check=check,capture_output=True,text=True)

def install():
    for name in ('data','logs'):
        (ROOT/name).mkdir(parents=True,exist_ok=True,mode=0o700)
    d={'Label':LABEL,'ProgramArguments':[str(ROOT/'.venv/bin/python'),'-m','app'],
       'WorkingDirectory':str(ROOT),'RunAtLoad':True,'KeepAlive':True,'ThrottleInterval':30,
       'ExitTimeOut':30,'Umask':63,
       'EnvironmentVariables':{'PATH':os.pathsep.join([str(ROOT/'.venv/bin'),str(Path.home()/'.local/bin'),os.environ.get('PATH',''),'/opt/homebrew/bin','/usr/local/bin','/usr/bin','/bin','/usr/sbin','/sbin']),'PYTHONUNBUFFERED':'1'},
       'StandardOutPath':str(ROOT/'logs/launchd.out.log'),'StandardErrorPath':str(ROOT/'logs/launchd.err.log')}
    PLIST.parent.mkdir(exist_ok=True);PLIST.write_bytes(plistlib.dumps(d));PLIST.chmod(0o600)
    command('bootout',DOMAIN+'/'+LABEL,check=False)
    # launchd can still be unloading the previous process after bootout returns.
    for attempt in range(60):
        result=command('bootstrap',DOMAIN,str(PLIST),check=False)
        if result.returncode==0:break
        if result.returncode!=5 or attempt==59:
            result.check_returncode()
        time.sleep(0.5)
    print('Installed',LABEL)

def main():
    if sys.prefix==sys.base_prefix:raise SystemExit('Use .venv/bin/python')
    action=sys.argv[1] if len(sys.argv)>1 else 'status'
    if action=='install':install()
    elif action=='start':
        result=command('print',DOMAIN+'/'+LABEL,check=False)
        if result.returncode:command('bootstrap',DOMAIN,str(PLIST))
        else:command('kickstart',DOMAIN+'/'+LABEL)
        print('Started')
    elif action=='stop':command('bootout',DOMAIN+'/'+LABEL,check=False);print('Stopped')
    elif action=='restart':command('kickstart','-k',DOMAIN+'/'+LABEL);print('Restarted')
    elif action=='uninstall':command('bootout',DOMAIN+'/'+LABEL,check=False);PLIST.unlink(missing_ok=True);print('Uninstalled service; source and credentials preserved')
    elif action=='status':
        r=command('print',DOMAIN+'/'+LABEL,check=False)
        print('\n'.join(line.strip() for line in r.stdout.splitlines() if any(x in line for x in ('state =','pid =','last exit','program ='))))
        if r.returncode:print('Service is not loaded')
    else:raise SystemExit('install | start | stop | restart | status | uninstall')
if __name__=='__main__':main()
