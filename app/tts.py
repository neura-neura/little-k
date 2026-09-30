import asyncio
import tempfile
import shutil
from pathlib import Path

class TTS:
    def __init__(self,config):self.config=config
    async def synthesize(self,text,language):
        language=language.split('-')[0]
        voice=self.config.voices.get(language)
        if not voice:raise ValueError('No configured voice for language')
        directory=Path(tempfile.mkdtemp(prefix='little-k-',dir=self.config.db.parent))
        source=directory/'speech.txt';source.write_text(text,encoding='utf-8');source.chmod(0o600)
        aiff=directory/'speech.aiff';wav=directory/'speech.wav'
        try:
            await self.run('/usr/bin/say','-v',voice,'-r',str(self.config.rate),'-f',str(source),'-o',str(aiff))
            await self.run(self.config.ffmpeg,'-nostdin','-hide_banner','-loglevel','error','-y','-i',str(aiff),'-af','adelay=750:all=1,apad=pad_dur=0.5','-ar','48000','-ac','2','-c:a','pcm_s16le',str(wav))
            if not wav.exists() or wav.stat().st_size<=44:raise ValueError('Empty audio')
            return wav
        except BaseException:shutil.rmtree(directory,ignore_errors=True);raise
    async def run(self,*args):
        p=await asyncio.create_subprocess_exec(*args,stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.DEVNULL)
        try:
            if await asyncio.wait_for(p.wait(),120):raise RuntimeError('Audio process failed')
        except BaseException:
            if p.returncode is None:p.kill();await p.wait()
            raise
    @staticmethod
    def cleanup(path):shutil.rmtree(path.parent,ignore_errors=True)
