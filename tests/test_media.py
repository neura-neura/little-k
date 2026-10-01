import asyncio
import json
from pathlib import Path
import sys
from dataclasses import replace
from unittest.mock import AsyncMock
import httpx
import pytest
from app.config import Config
from app.media import Media, MediaError, MediaItem, platform
from app.netease import NetEase, extract_type_and_id

@pytest.mark.parametrize('url,source',[
    ('https://youtu.be/a','youtube'),('https://music.youtube.com/watch?v=a','youtube'),
    ('https://b23.tv/a','bilibili'),('https://music.163.com/#/song?id=123','netease'),
    ('https://open.spotify.com/track/a','spotify'),
    ('https://youtube.com.evil.example/a',None),('http://localhost/a',None),
    ('file:///etc/passwd',None),('https://user:password@youtube.com/a',None),
    ('https://youtube.com:5000/a',None),('https://youtube.com:bad/a',None),('https://[invalid',None)])
def test_source_allowlist(url,source):assert platform(url)==source

@pytest.mark.asyncio
async def test_ytdlp_uses_private_cookie_copy_and_no_shell(tmp_path):
    original=tmp_path/'original.txt';original.write_text('# Netscape HTTP Cookie File\n')
    cfg=replace(Config.load(),youtube_cookies=original)
    m=Media(cfg);folder=tmp_path/'download';folder.mkdir()
    try:
        args=m.ytdlp('https://youtu.be/a',folder)
        jar=Path(args[args.index('--cookies')+1])
        assert jar!=original and jar.read_text()==original.read_text()
        assert jar.stat().st_mode&0o077==0
        assert '--ignore-config' in args and '--no-playlist' in args
        assert args[-2:]==['--','https://youtu.be/a']
    finally:await m.close()

@pytest.mark.asyncio
async def test_cancelled_download_cleans_temp_directory(tmp_path):
    cfg=replace(Config.load(),db=tmp_path/'state.sqlite3')
    m=Media(cfg);started=asyncio.Event()
    async def pending(*args,**kwargs):started.set();await asyncio.Event().wait()
    m.command=pending
    task=asyncio.create_task(m.prepare(MediaItem('test',url='https://youtu.be/a')))
    try:
        await started.wait();task.cancel()
        with pytest.raises(asyncio.CancelledError):await task
        assert not list(tmp_path.glob('little-k-media-*'))
    finally:await m.close()

@pytest.mark.asyncio
async def test_netease_cookies_not_sent_to_audio_host(tmp_path):
    cookie=tmp_path/'cookie.json';cookie.write_text(json.dumps([{'domain':'.music.163.com','name':'MUSIC_U','value':'fake-private-cookie'}]))
    cfg=replace(Config.load(),netease_cookies=cookie);m=Media(cfg);seen=[]
    async def handle(request):
        seen.append(request)
        if request.url.host.endswith('music.163.com'):return httpx.Response(200,json={'data':[{'url':'https://m.music.126.net/test.mp3'}]})
        return httpx.Response(200,content=b'audio')
    await m.http.aclose();m.http=httpx.AsyncClient(transport=httpx.MockTransport(handle))
    m.netease.http=m.http
    try:
        url=await m.netease.song_url(123)
        await m.download_netease(url,tmp_path/'audio.mp3')
        assert 'fake-private-cookie' in seen[0].headers['cookie']
        assert 'cookie' not in seen[1].headers and 'authorization' not in seen[1].headers
    finally:await m.close()

@pytest.mark.asyncio
async def test_download_failure_is_redacted(tmp_path):
    m=Media(Config.load())
    try:
        with pytest.raises(MediaError) as failure:
            await m.command(sys.executable,'-c','import sys; print("private-cookie",file=sys.stderr); sys.exit(1)')
        assert 'private-cookie' not in str(failure.value)
    finally:await m.close()

@pytest.mark.parametrize('url,expected',[
    ('https://music.163.com/#/song?id=123',('song','123')),
    ('https://music.163.com/playlist?id=456',('playlist','456')),
    ('https://music.163.com/album/789',('album','789'))])
def test_old_netease_url_forms(url,expected):assert extract_type_and_id(url)==expected

@pytest.mark.asyncio
async def test_long_video_returns_explanation_without_cookie_retry(tmp_path):
    cfg=replace(Config.load(),db=tmp_path/'state.db',media_max_duration=1800)
    m=Media(cfg);m.command=AsyncMock(return_value=json.dumps({'duration':2641,'is_live':False}).encode())
    try:
        with pytest.raises(MediaError,match='44 minutes long.*30 minutes'):
            await m.prepare(MediaItem('test',url='https://youtu.be/test'))
        assert m.command.await_count==1
        assert '--skip-download' in m.command.call_args.args
        assert not list(tmp_path.glob('little-k-media-*'))
    finally:await m.close()

@pytest.mark.asyncio
async def test_completed_live_video_allowed_but_live_stream_rejected(tmp_path):
    m=Media(replace(Config.load(),db=tmp_path/'state.db'))
    m.command=AsyncMock(return_value=json.dumps({'duration':5,'is_live':True}).encode())
    try:
        with pytest.raises(MediaError,match='Live streams'):
            await m.prepare(MediaItem('test',url='https://youtu.be/test'))
        assert m.command.await_count==1
    finally:await m.close()
