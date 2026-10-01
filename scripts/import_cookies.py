"""Import browser Cookie headers or cookie exports without printing credentials."""
import argparse
from http.cookiejar import Cookie, MozillaCookieJar
import json
import os
from pathlib import Path
from app.config import ROOT


def read_cookies(path,domain):
    text=Path(path).read_text(encoding='utf-8').strip()
    if not text:raise ValueError('Empty cookie export')
    if text.startswith(('[','{')):
        data=json.loads(text)
        if isinstance(data,dict):data=[{'name':k,'value':v,'domain':domain} for k,v in data.items() if isinstance(v,str)]
        if not isinstance(data,list):raise ValueError('Unsupported JSON cookie export')
        return [dict(row,domain=row.get('domain') or domain) for row in data
                if isinstance(row,dict) and isinstance(row.get('name'),str) and isinstance(row.get('value'),str)]
    if text.startswith('#') or '\t' in text:
        jar=MozillaCookieJar(str(path));jar.load(ignore_discard=True,ignore_expires=True)
        return [{'name':c.name,'value':c.value,'domain':c.domain,'path':c.path,'secure':c.secure,'expirationDate':c.expires} for c in jar]
    # Browser request-header exports use semicolons; split only the first '='.
    if text.lower().startswith('cookie:'):text=text.split(':',1)[1].strip()
    rows=[]
    for item in text.split(';'):
        if not item.strip():continue
        name,sep,value=item.strip().partition('=')
        if not sep or not name or any(c in name+value for c in ('\r','\n','\t')):
            raise ValueError('Invalid Cookie header export')
        rows.append({'name':name,'value':value,'domain':domain})
    return rows


def write_netscape(rows,destination):
    jar=MozillaCookieJar(str(destination))
    for row in rows:
        domain=row['domain']
        expires=row.get('expirationDate') or None
        jar.set_cookie(Cookie(0,row['name'],row['value'],None,False,domain,True,domain.startswith('.'),
                              row.get('path') or '/',True,bool(row.get('secure',True)),
                              int(expires) if expires else None,not bool(expires),None,None,{},False))
    jar.save(ignore_discard=True,ignore_expires=True)
    Path(destination).chmod(0o600)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bilibili',type=Path)
    parser.add_argument('--netease',type=Path)
    args=parser.parse_args()
    if not args.bilibili and not args.netease:parser.error('Provide --bilibili and/or --netease')
    os.umask(0o077)
    target=ROOT/'secrets/cookies';target.mkdir(parents=True,exist_ok=True,mode=0o700)
    for source,domain,name in [(args.bilibili,'.bilibili.com','bilibili.txt'),(args.netease,'.music.163.com','netease.json')]:
        if source is None:continue
        rows=read_cookies(source,domain)
        if not rows:raise SystemExit('No cookies found in export')
        rows=[r for r in rows if r['domain'].lstrip('.')==domain.lstrip('.') or r['domain'].endswith(domain)]
        if not rows:raise SystemExit('Cookie export does not match the requested platform')
        output=target/name
        if name.endswith('.json'):
            output.write_text(json.dumps(rows,ensure_ascii=False),encoding='utf-8');output.chmod(0o600)
        else:write_netscape(rows,output)
        print(name+': imported '+str(len(rows))+' cookies; private permissions applied.')

if __name__=='__main__':main()
