import json
from http.cookiejar import MozillaCookieJar
from scripts.import_cookies import read_cookies,write_netscape
from app.netease import NetEase


def test_bilibili_header_converted_without_losing_equals(tmp_path):
    source=tmp_path/'header.txt';source.write_text('Cookie: SESSDATA=fake%2Btoken==; bili_jct=fake-csrf')
    rows=read_cookies(source,'.bilibili.com');destination=tmp_path/'cookies.txt'
    write_netscape(rows,destination)
    jar=MozillaCookieJar(str(destination));jar.load(ignore_discard=True,ignore_expires=True)
    values={c.name:c.value for c in jar}
    assert values=={'SESSDATA':'fake%2Btoken==','bili_jct':'fake-csrf'}
    assert all(c.domain=='.bilibili.com' for c in jar)
    assert destination.stat().st_mode&0o077==0


def test_netease_header_converted_to_supported_json(tmp_path):
    source=tmp_path/'header.txt';source.write_text('MUSIC_U=fake-auth==; __csrf=fake-csrf')
    rows=read_cookies(source,'.music.163.com');destination=tmp_path/'netease.json'
    destination.write_text(json.dumps(rows))
    assert NetEase(None,destination).cookies()=={'MUSIC_U':'fake-auth==','__csrf':'fake-csrf'}


def test_import_accepts_netscape_and_json(tmp_path):
    cookie=tmp_path/'cookies.txt'
    write_netscape([{'name':'test','value':'fake','domain':'.bilibili.com'}],cookie)
    assert read_cookies(cookie,'.bilibili.com')[0]['value']=='fake'
    cookie.write_text('{"test":"fake"}')
    assert read_cookies(cookie,'.music.163.com')==[{'name':'test','value':'fake','domain':'.music.163.com'}]
