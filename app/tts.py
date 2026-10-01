import asyncio
import tempfile
import shutil
import sys
from pathlib import Path

# Same gTTS domains/presets as the previous tgcall-tts-userbot.
ACCENTS = {'default':'com','uk':'co.uk','au':'com.au','ie':'ie','in':'co.in',
           'mx':'com.mx','es':'es'}

class TTS:
    def __init__(self,config):self.config=config
    async def synthesize(self,text,language,backend='macos',accent='default'):
        language=language.split('-')[0].lower()
        if backend not in ('macos','gtts') or accent not in ACCENTS:
            raise ValueError('Unknown voice preset')
        self.config.db.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        directory=Path(tempfile.mkdtemp(prefix='little-k-',dir=self.config.db.parent))
        source=directory/'speech.txt';source.write_text(text,encoding='utf-8');source.chmod(0o600)
        wav=directory/'speech.wav'
        try:
            if backend=='macos':
                voice=self.config.voices.get(language)
                if not voice:raise ValueError('No configured voice for language')
                audio=directory/'speech.aiff'
                await self.run('/usr/bin/say','-v',voice,'-r',str(self.config.rate),'-f',str(source),'-o',str(audio))
            else:
                audio=directory/'speech.mp3'
                await self.run(sys.executable,'-m','scripts.gtts_synthesize',str(source),str(audio),
                               'zh-CN' if language=='zh' else language,ACCENTS[accent])
            await self.run(self.config.ffmpeg,'-nostdin','-hide_banner','-loglevel','error','-y','-i',str(audio),'-af','adelay=750:all=1,apad=pad_dur=0.5','-ar','48000','-ac','2','-c:a','pcm_s16le',str(wav))
            if not wav.exists() or wav.stat().st_size<=44:raise ValueError('Empty audio')
            return wav
        except BaseException:shutil.rmtree(directory,ignore_errors=True);raise
    async def run(self,*args):
        p=await asyncio.create_subprocess_exec(*args,stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.DEVNULL)
        try:
            if await asyncio.wait_for(p.wait(),120):raise RuntimeError('Audio process failed')
        except BaseException:
            if p.returncode is None:
                p.kill();await p.wait()
            raise
    @staticmethod
    def cleanup(path):shutil.rmtree(path.parent,ignore_errors=True)
