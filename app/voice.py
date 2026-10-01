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
from .tts import TTS, ACCENTS
from .media import Media, MediaItem, MediaError

log=logging.getLogger(__name__)
@dataclass
class Job:
    id:str
    chat:int
    message:int
    text:str=''
    language:str='es'
    backend:str='macos'
    accent:str='default'
    media:MediaItem | None=None
    collection:str | None=None
    index:int=0

class Voice:
    def __init__(self,client,config,storage,notify):
        self.config=config;self.storage=storage;self.notify=notify
        self.calls=PyTgCalls(client);self.tts=TTS(config);self.media=Media(config)
        self.queues={};self.workers={};self.finished={};self.connected=set();self.current={}
        self.paused=set();self.pause_started={};self.pause_time={}
        self.on_media_done=None;self.closing=False
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
    def preset(self):
        return self.storage.setting('voice_profile',{'backend':'macos','accent':'default'})
    def set_preset(self,backend,accent='default'):
        if backend not in ('macos','gtts') or accent not in ACCENTS or (backend=='macos' and accent!='default'):
            raise ValueError('Use .voice macos or .voice gtts [default|mx|es|uk|au|ie|in].')
        self.storage.set_setting('voice_profile',{'backend':backend,'accent':accent})
    def _enqueue(self,job):
        if getattr(self,'closing',False):raise ValueError('Voice service is closing')
        if not self.config.voice_enabled:raise ValueError('Voice disabled')
        if job.chat>=0:raise ValueError('Voice requires a group chat')
        chat=job.chat;queue=self.queues.setdefault(chat,asyncio.Queue(maxsize=20))
        queue.put_nowait(job);self.storage.voice(job.id,chat,job.message,'queued')
        if chat not in self.workers or self.workers[chat].done():
            self.workers[chat]=asyncio.create_task(self._worker(chat))
            self.workers[chat].add_done_callback(lambda task:self._restart_pending(chat))
    def enqueue(self,chat,message,text,language):
        preset=self.preset()
        self._enqueue(Job(uuid.uuid4().hex,chat,message,text,language,preset['backend'],preset['accent']))
    def enqueue_media(self,chat,message,item,collection=None,index=0):
        self._enqueue(Job(uuid.uuid4().hex,chat,message,media=item,collection=collection,index=index))
    def _restart_pending(self,chat):
        if getattr(self,'closing',False):return
        # A message can arrive while the idle worker is awaiting leave_call.
        if self.queues[chat].empty():return
        active=self.workers.get(chat)
        if active and not active.done():return
        task=asyncio.create_task(self._worker(chat));self.workers[chat]=task
        task.add_done_callback(lambda _:self._restart_pending(chat))
    async def _wait_audio(self,chat,duration):
        # Pausing extends the playback deadline; a paused song is not an idle call.
        deadline=time.monotonic()+duration+30
        last=time.monotonic()
        while not self.finished[chat].is_set():
            try:await asyncio.wait_for(self.finished[chat].wait(),1)
            except asyncio.TimeoutError:pass
            now=time.monotonic()
            if chat in self.paused:deadline+=now-last
            elif now>deadline:raise asyncio.TimeoutError('Audio playback timed out')
            last=now
    async def _worker(self,chat):
        queue=self.queues[chat]
        try:
            while True:
                try:job=await asyncio.wait_for(queue.get(),self.config.idle_timeout)
                except asyncio.TimeoutError:break
                self.current[chat]=job;path=None;completed=False
                try:
                    if not self.started:await self.start()
                    # Join an existing call before spending time synthesizing/downloading.
                    if chat not in self.connected:
                        await self.calls.play(chat,None,GroupCallConfig(auto_start=False))
                        self.connected.add(chat)
                        await asyncio.sleep(1)
                    if job.media:
                        log.info('Media preparing chat=%s',chat)
                        path=await asyncio.wait_for(self.media.prepare(job.media),self.config.media_timeout)
                    else:
                        log.info('TTS started chat=%s language=%s backend=%s',chat,job.language,job.backend)
                        path=await self.tts.synthesize(job.text,job.language,backend=job.backend,accent=job.accent)
                    self.finished[chat]=asyncio.Event()
                    self.paused.discard(chat);self.pause_time[chat]=0
                    self.storage.voice(job.id,chat,job.message,'playing')
                    pcm=path.with_suffix('.pcm')
                    with wave.open(str(path)) as audio, pcm.open('wb') as raw:
                        if (audio.getframerate(),audio.getnchannels(),audio.getsampwidth())!=(48000,2,2):
                            raise ValueError('Playback requires 48 kHz stereo signed 16-bit PCM')
                        duration=audio.getnframes()/audio.getframerate()
                        while frames:=audio.readframes(65536):raw.write(frames)
                    pcm.chmod(0o600)
                    stream=Stream(microphone=AudioStream(MediaSource.FILE,str(pcm),AudioParameters(48000,2)))
                    playback_start=time.monotonic()
                    await self.calls.play(chat,stream,GroupCallConfig(auto_start=False))
                    await self.calls.unmute(chat)
                    if job.media:
                        try:await self.notify(chat,'Now playing: '+job.media.title,job.message)
                        except Exception:log.warning('Media notification failed')
                    log.info('Audio sending chat=%s duration=%.2fs',chat,duration)
                    await self._wait_audio(chat,duration)
                    elapsed=time.monotonic()-playback_start-self.pause_time.get(chat,0)
                    if elapsed<max(0.2,duration-1.0):raise RuntimeError('Audio stream ended before playback duration')
                    self.storage.voice(job.id,chat,job.message,'done');completed=True
                    log.info('Audio playback completed chat=%s elapsed=%.2fs',chat,elapsed)
                except asyncio.CancelledError:
                    if path is None and job.media:
                        log.info('Media preparation cancelled chat=%s',chat)
                    self.storage.voice(job.id,chat,job.message,'cancelled');raise
                except Exception as exc:
                    self.storage.voice(job.id,chat,job.message,'failed')
                    log.warning('Voice failed chat=%s type=%s',chat,type(exc).__name__)
                    from pytgcalls.exceptions import NoActiveGroupCall
                    if isinstance(exc,NoActiveGroupCall):text='no hay una llamada activa en este grupo 🐈'
                    elif isinstance(exc,MediaError):text=str(exc)
                    elif job.media:text='I could not play that media. Check the link, cookies and account availability.'
                    else:text='no pude leerlo en la llamada 🐈'
                    try:await self.notify(chat,text,job.message)
                    except Exception:log.warning('Voice error notification failed')
                    await self._leave(chat)
                finally:
                    if path:self.tts.cleanup(path)
                    self.paused.discard(chat);self.pause_started.pop(chat,None);self.pause_time.pop(chat,None)
                    self.current.pop(chat,None);queue.task_done()
                if job.media and self.on_media_done:
                    try:await self.on_media_done(job,completed)
                    except Exception:log.warning('Collection advance failed chat=%s',chat)
        finally:await self._leave(chat)
    async def _leave(self,chat):
        if chat in self.connected:
            try:await self.calls.leave_call(chat)
            except Exception as exc:log.warning('Voice leave failed type=%s',type(exc).__name__)
            self.connected.discard(chat);log.info('Voice chat disconnected chat=%s',chat)
        self.finished.pop(chat,None)
        self.paused.discard(chat)
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
    async def pause(self,chat):
        if chat not in self.finished or self.finished[chat].is_set():raise ValueError('There is no audio playing.')
        if chat not in self.paused:
            if not await self.calls.pause(chat):raise ValueError('Could not pause this stream.')
            self.paused.add(chat);self.pause_started[chat]=time.monotonic()
    async def resume(self,chat):
        if chat in self.paused:
            if not await self.calls.resume(chat):raise ValueError('Could not resume this stream.')
            self.pause_time[chat]=self.pause_time.get(chat,0)+time.monotonic()-self.pause_started.pop(chat,time.monotonic())
            self.paused.discard(chat)
    def status(self,chat):
        job=self.current.get(chat)
        return {'connected':chat in self.connected,'queued':self.queues[chat].qsize() if chat in self.queues else 0,
                'playing':chat in self.finished,'preparing':job is not None and chat not in self.finished,
                'paused':chat in self.paused,'current':job.media.title if job and job.media else 'speech' if job else None,
                **self.preset()}
    async def close(self):
        if getattr(self,'closing',False):return
        self.closing=True
        try:
            for chat in set(self.workers)|set(self.connected):await self.stop(chat)
        finally:
            # PyTgCalls 3.0 has no public whole-client shutdown method. Its native
            # callbacks capture PyTgCalls, creating a cycle back to _binding.
            # Release NTgCalls while Python and its event loop are still alive:
            # deferred C++ LogSink teardown at process exit aborts on macOS.
            self.calls._is_running=False
            self.calls._binding=None
            executor=getattr(self.calls,'executor',None)
            if executor:await asyncio.to_thread(executor.shutdown,wait=True,cancel_futures=True)
            self.started=False
            await self.media.close()
            log.info('Voice native resources released')
