"""Private, cancellable audio downloads with the previous bot's source adapters."""
import asyncio
from dataclasses import dataclass
import json
import os
import signal
from pathlib import Path
import re
import shutil
import sys
import tempfile
from urllib.parse import urlparse
import wave
import httpx
from .netease import NetEase


class MediaError(ValueError):pass


class MediaLimitError(MediaError):pass


DOMAINS={'youtube':('youtube.com','youtu.be'), 'bilibili':('bilibili.com','b23.tv'),
         'netease':('music.163.com',),'spotify':('open.spotify.com','spotify.link')}


def platform(url):
    try:
        parsed=urlparse(url)
        if parsed.scheme not in ('http','https') or parsed.username or parsed.port not in (None,80,443):return None
        host=(parsed.hostname or '').lower()
    except ValueError:return None
    return next((name for name,domains in DOMAINS.items()
                 if any(host==domain or host.endswith('.'+domain) for domain in domains)),None)


def bare_url(text):
    text=(text or '').strip()
    return text if not re.search(r'\s',text) and platform(text) else None


@dataclass(frozen=True)
class MediaItem:
    title:str
    url:str=''
    song:dict | None=None


class Media:
    def __init__(self,config):
        self.config=config
        self.http=httpx.AsyncClient(timeout=httpx.Timeout(30,connect=10),trust_env=False,follow_redirects=False)
        self.netease=NetEase(self.http,config.netease_cookies,config.media_max_tracks)
        self.slots=asyncio.Semaphore(2)

    async def command(self,*args,timeout=None,capture=False):
        # No shell interpolation or arbitrary commands. Suppress extractor output,
        # which can include signed URLs, cookie paths or authentication details.
        p=await asyncio.create_subprocess_exec(*args,stdout=asyncio.subprocess.PIPE if capture else asyncio.subprocess.DEVNULL,
                                                stderr=asyncio.subprocess.DEVNULL,start_new_session=True)
        try:
            stdout,_=await asyncio.wait_for(p.communicate(),timeout or self.config.media_timeout)
            if p.returncode:raise MediaError('The source could not be downloaded. Check cookies, availability and the media URL.')
            return stdout if capture else None
        except BaseException:
            if p.returncode is None:
                try:os.killpg(p.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                await p.wait()
            raise

    def ytdlp(self,url,directory,cookies=True,metadata=False):
        source=platform(url)
        if source not in ('youtube','bilibili'):raise MediaError('Unsupported direct media source.')
        args=[sys.executable,'-m','yt_dlp','--ignore-config','--no-cache-dir','--no-playlist',
              '--no-progress','--no-warnings','--playlist-items','1','--socket-timeout','20','--retries','2','--extractor-retries','2',
              '--ffmpeg-location',self.config.ffmpeg]
        runtime=shutil.which('deno') or shutil.which('node')
        if runtime:args+=['--js-runtimes',('deno' if Path(runtime).name=='deno' else 'node')+':'+runtime]
        cookie_path=self.config.youtube_cookies if source=='youtube' else self.config.bilibili_cookies
        if cookies and cookie_path and cookie_path.is_file():
            # yt-dlp can update cookie jars: use a private copy per request.
            jar=directory/'cookies.txt';shutil.copyfile(cookie_path,jar);jar.chmod(0o600)
            args+=['--cookies',str(jar)]
        args+=['--match-filter',f'!is_live & duration <=? {self.config.media_max_duration}',
               '--max-filesize',str(self.config.media_max_bytes)]
        if metadata:args+=['--skip-download','--dump-single-json']
        else:args+=['--no-simulate','-f','bestaudio[ext=m4a]/bestaudio/best' if source=='youtube' else 'bestaudio/best',
                    '-o',str(directory/'source.%(ext)s'),'--print-to-file','title',str(directory/'title.txt')]
        return [*args,'--',url]

    async def prepare(self,item):
        async with self.slots:
            self.config.db.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            directory=Path(tempfile.mkdtemp(prefix='little-k-media-',dir=self.config.db.parent))
            try:
                if item.song:
                    url=await self.netease.song_url(item.song['id'])
                    source=directory/'source.mp3'
                    await self.download_netease(url,source)
                else:
                    for cookies in (True,False):
                        try:
                            metadata=await self.command(*self.ytdlp(item.url,directory,cookies,metadata=True),capture=True)
                            info=json.loads(metadata)
                            if info.get('is_live') or info.get('live_status') in ('is_live','is_upcoming'):
                                raise MediaLimitError('Live streams are not supported; use a finished video.')
                            duration=info.get('duration')
                            if duration is not None and float(duration)>self.config.media_max_duration:
                                raise MediaLimitError(f'This video is {float(duration)/60:.0f} minutes long; the configured limit is {self.config.media_max_duration/60:.0f} minutes. Increase MEDIA_MAX_DURATION to play it.')
                            await self.command(*self.ytdlp(item.url,directory,cookies))
                            sources=[p for p in directory.glob('source.*') if p.suffix not in ('.part','.ytdl','.temp')]
                            if not sources:raise MediaError('No audio file was produced.')
                            source=sources[0]
                            if source.stat().st_size>self.config.media_max_bytes:
                                raise MediaLimitError('Audio exceeds MEDIA_MAX_BYTES.')
                            break
                        except MediaLimitError:raise
                        except MediaError:
                            for file in directory.glob('source.*'):file.unlink(missing_ok=True)
                            if not cookies:raise
                output=directory/'audio.wav'
                await self.command(self.config.ffmpeg,'-nostdin','-hide_banner','-loglevel','error','-y',
                    '-i',str(source),'-t',str(self.config.media_max_duration+2),
                    '-af','adelay=750:all=1,apad=pad_dur=0.5','-ar','48000','-ac','2','-c:a','pcm_s16le',str(output))
                with wave.open(str(output)) as audio:
                    duration=audio.getnframes()/audio.getframerate()
                    if audio.getnchannels()!=2 or audio.getsampwidth()!=2 or audio.getframerate()!=48000 or duration<=1.25:
                        raise MediaError('Invalid or empty audio.')
                    if duration>self.config.media_max_duration+1.5:
                        raise MediaError('This audio exceeds MEDIA_MAX_DURATION.')
                for file in directory.iterdir():
                    if file!=output:file.unlink(missing_ok=True)
                return output
            except BaseException:shutil.rmtree(directory,ignore_errors=True);raise

    async def download_netease(self,url,path):
        parsed=urlparse(url);host=parsed.hostname or ''
        if parsed.scheme not in ('http','https') or not (host.endswith('.music.126.net') or host=='music.126.net'):
            raise MediaError('NetEase returned an unsupported audio host.')
        total=0
        # The download host gets no account cookies or Authorization headers.
        async with self.http.stream('GET',url) as response:
            response.raise_for_status()
            with path.open('wb') as file:
                async for chunk in response.aiter_bytes():
                    total+=len(chunk)
                    if total>self.config.media_max_bytes:raise MediaLimitError('Audio exceeds MEDIA_MAX_BYTES.')
                    file.write(chunk)
        if not total:raise MediaError('Empty NetEase audio.')

    async def spotify_query(self,url):
        if platform(url)!='spotify':raise MediaError('Unsupported Spotify URL.')
        for _ in range(5):
            if (urlparse(url).hostname or '')!='spotify.link':break
            response=await self.http.get(url)
            if response.is_redirect:
                from urllib.parse import urljoin
                url=urljoin(url,response.headers.get('location',''))
                if platform(url)!='spotify':raise MediaError('Spotify link redirected to an unsupported domain.')
            else:break
        parsed=urlparse(url)
        parts=[x for x in parsed.path.split('/') if x and not x.startswith('intl-') and x!='embed']
        if not parts or parts[0] not in ('track','album','playlist'):raise MediaError('Use a Spotify track, album or playlist link.')
        response=await self.http.get('https://open.spotify.com/oembed',params={'url':url})
        response.raise_for_status();data=response.json()
        title=(data.get('title') or '').strip()
        artist=(data.get('author_name') or '').strip()
        # Spotify oEmbed often gives only the track title. The original adapter
        # supplements artist metadata from the public page and its description.
        page=await self.http.get(url,headers={'User-Agent':'Mozilla/5.0'})
        if page.status_code==200:
            from html import unescape
            match=re.search(r'<title>(.*?)</title>',page.text,re.I|re.S)
            if match:
                page_title=unescape(match[1])
                artist_match=re.search(r' - (?:song and lyrics|album|single|ep|playlist) by (.*?)\s*(?:\| Spotify)?$',page_title,re.I)
                if artist_match:artist=artist_match[1].strip()
            if not artist:
                match=re.search(r'<meta[^>]+(?:property|name)=["\'](?:og:description|twitter:description)["\'][^>]+content=["\']([^"\']+)',page.text,re.I)
                if match:
                    fields=unescape(match[1]).split('·')
                    if len(fields)>=2:artist=fields[0].strip()
        query=' '.join(x for x in (title,artist) if x)
        if not query:raise MediaError('Could not read Spotify metadata.')
        return query

    async def close(self):await self.http.aclose()
