import asyncio
import logging
import uuid
import wave
import time
from ntgcalls import MediaSource
from pytgcalls.types.raw import Stream,AudioStream,AudioParameters
from dataclasses import dataclass
from pytgcalls import PyTgCalls, filters
from pytgcalls.types import GroupCallConfig, StreamEnded, Device
from .tts import TTS

log=logging.getLogger(__name__)
@dataclass
class Job:
    id:str
    chat:int
    message:int
    text:str
    language:str

class Voice:
    def __init__(self,client,config,storage,notify):
        self.config=config;self.storage=storage;self.notify=notify
        self.calls=PyTgCalls(client);self.tts=TTS(config)
        self.queues={};self.workers={};self.finished={};self.connected=set();self.current={}
        self.started=False;self.start_lock=asyncio.Lock()
        self.calls.on_update(filters.stream_end(StreamEnded.Type.AUDIO,Device.MICROPHONE))(self._ended)
    async def _ended(self,client,update):
        event=self.finished.get(update.chat_id)
        if event:event.set()
    async def start(self):
        async with self.start_lock:
            if self.started:return
            await self.calls.start();self.started=True
            log.info('Voice library initialized: PyTgCalls / NTgCalls')
    def enqueue(self,chat,message,text,language):
        if not self.config.voice_enabled:raise ValueError('Voice disabled')
        if chat>=0:raise ValueError('Voice requires a group chat')
        queue=self.queues.setdefault(chat,asyncio.Queue(maxsize=20))
        job=Job(uuid.uuid4().hex,chat,message,text,language)
        queue.put_nowait(job);self.storage.voice(job.id,chat,message,'queued')
        if chat not in self.workers or self.workers[chat].done():
            self.workers[chat]=asyncio.create_task(self._worker(chat))
            self.workers[chat].add_done_callback(lambda task:self._restart_pending(chat))
    def _restart_pending(self,chat):
        # A message can arrive while the idle worker is awaiting leave_call.
        if self.queues[chat].empty():return
        task=asyncio.create_task(self._worker(chat));self.workers[chat]=task
        task.add_done_callback(lambda _:self._restart_pending(chat))
    async def _worker(self,chat):
        queue=self.queues[chat]
        try:
            while True:
                try:job=await asyncio.wait_for(queue.get(),self.config.idle_timeout)
                except asyncio.TimeoutError:break
                self.current[chat]=job;path=None
                try:
                    if not self.started:await self.start()
                    log.info('TTS started chat=%s language=%s',chat,job.language)
                    path=await self.tts.synthesize(job.text,job.language)
                    if chat not in self.connected:
                        await self.calls.play(chat,None,GroupCallConfig(auto_start=False))
                        self.connected.add(chat)
                        # Establish WebRTC before the short TTS clip is consumed.
                        await asyncio.sleep(1)
                    self.finished[chat]=asyncio.Event()
                    self.storage.voice(job.id,chat,job.message,'playing')
                    # Critical: PyTgCalls defaults auto_start=True. Explicitly forbid creation.
                    # Native raw PCM file reader avoids shell/pipe startup failures on macOS.
                    pcm=path.with_suffix('.pcm')
                    with wave.open(str(path)) as audio:
                        duration=audio.getnframes()/audio.getframerate()
                        pcm.write_bytes(audio.readframes(audio.getnframes()))
                    stream=Stream(microphone=AudioStream(MediaSource.FILE,str(pcm),AudioParameters(48000,2)))
                    playback_start=time.monotonic()
                    await self.calls.play(chat,stream,GroupCallConfig(auto_start=False))
                    await self.calls.unmute(chat)
                    self.connected.add(chat);log.info('Voice chat connected chat=%s',chat)
                    with wave.open(str(path)) as audio:duration=audio.getnframes()/audio.getframerate()
                    log.info('Audio sending chat=%s duration=%.2fs',chat,duration)
                    await asyncio.wait_for(self.finished[chat].wait(),duration+30)
                    elapsed=time.monotonic()-playback_start
                    if elapsed < max(0.2,duration-1.0):raise RuntimeError('Audio stream ended before playback duration')
                    self.storage.voice(job.id,chat,job.message,'done');log.info('Audio playback completed chat=%s elapsed=%.2fs',chat,elapsed)
                except asyncio.CancelledError:
                    self.storage.voice(job.id,chat,job.message,'cancelled');raise
                except Exception as exc:
                    self.storage.voice(job.id,chat,job.message,'failed')
                    log.warning('Voice failed chat=%s type=%s',chat,type(exc).__name__)
                    from pytgcalls.exceptions import NoActiveGroupCall
                    text='no hay una llamada activa en este grupo 🐈' if isinstance(exc,NoActiveGroupCall) else 'no pude leerlo en la llamada 🐈'
                    try:await self.notify(chat,text,job.message)
                    except Exception:log.warning('Voice error notification failed')
                    await self._leave(chat)
                finally:
                    if path:self.tts.cleanup(path)
                    self.current.pop(chat,None);queue.task_done()
        finally:
            await self._leave(chat)
    async def _leave(self,chat):
        if chat in self.connected:
            try:await self.calls.leave_call(chat)
            except Exception as exc:log.warning('Voice leave failed type=%s',type(exc).__name__)
            self.connected.discard(chat);log.info('Voice chat disconnected chat=%s',chat)
        self.finished.pop(chat,None)
    def clear(self,chat):
        queue=self.queues.get(chat);count=0
        if queue:
            while not queue.empty():
                job=queue.get_nowait();self.storage.voice(job.id,chat,job.message,'cancelled');queue.task_done();count+=1
        return count
    async def stop(self,chat):
        self.clear(chat)
        worker=self.workers.get(chat)
        if worker and not worker.done():
            worker.cancel()
            try:await worker
            except asyncio.CancelledError:pass
        await self._leave(chat)
    def status(self,chat):
        return {'connected':chat in self.connected,'queued':self.queues[chat].qsize() if chat in self.queues else 0,'playing':chat in self.current}
    async def close(self):
        for chat in list(self.workers):await self.stop(chat)
