import asyncio
import wave
from types import SimpleNamespace
from unittest.mock import AsyncMock
from dataclasses import replace
import pytest
from app.voice import Voice
from app.config import Config
from app.storage import Storage
from pytgcalls.exceptions import NoActiveGroupCall

@pytest.fixture
def voice(tmp_path):
    cfg=replace(Config.load(),idle_timeout=.03)
    v=object.__new__(Voice);v.config=cfg;v.storage=Storage(tmp_path/'db');v.notify=AsyncMock()
    v.queues={};v.workers={};v.finished={};v.connected=set();v.current={};v.started=True
    v.paused=set();v.pause_started={};v.pause_time={};v.on_media_done=None
    v.calls=SimpleNamespace(play=AsyncMock(),leave_call=AsyncMock(),unmute=AsyncMock())
    path=tmp_path/'audio.wav'
    with wave.open(str(path),'wb') as w:w.setnchannels(2);w.setsampwidth(2);w.setframerate(48000);w.writeframes(b'\0'*1920)
    v.tts=SimpleNamespace(synthesize=AsyncMock(return_value=path),cleanup=lambda _:None)
    yield v;v.storage.close()

@pytest.mark.asyncio
async def test_no_call_never_creates(voice):
    v=voice;v.calls.play.side_effect=NoActiveGroupCall()
    v.enqueue(-100,1,'hola','es');await v.workers[-100]
    config=v.calls.play.call_args[0][2];assert config.auto_start is False
    assert v.notify.await_count==1
    assert v.storage.db.execute('SELECT status FROM voice_jobs').fetchone()[0]=='failed'

@pytest.mark.asyncio
async def test_queue_order_and_idle_leave(voice):
    v=voice;order=[]
    async def play(chat,path,config):
        if path is not None:
            order.append(v.current[chat].message);await asyncio.sleep(.21);v.finished[chat].set()
    v.calls.play.side_effect=play
    v.enqueue(-100,1,'uno','es');v.enqueue(-100,2,'二','zh')
    await v.workers[-100]
    assert order==[1,2]
    assert v.calls.leave_call.await_count==1
    assert not v.connected
    assert [r[0] for r in v.storage.db.execute('SELECT status FROM voice_jobs')]==['done','done']

@pytest.mark.asyncio
async def test_tts_failure_survives_next_job(voice):
    v=voice;path=v.tts.synthesize.return_value
    v.tts.synthesize.side_effect=[RuntimeError('TTS failure'),path]
    async def play(chat,path,config):
        if path is not None:await asyncio.sleep(.21);v.finished[chat].set()
    v.calls.play.side_effect=play
    v.enqueue(-100,1,'uno','es');v.enqueue(-100,2,'two','en');await v.workers[-100]
    assert v.notify.await_count==1 and v.calls.play.await_count==3

def test_reject_private_calls(voice):
    with pytest.raises(ValueError):voice.enqueue(123,1,'hola','es')

@pytest.mark.asyncio
async def test_voice_selection_is_snapshotted_when_queued(voice):
    v=voice;v.connected.add(-100)
    async def play(chat,path,config):
        if path is not None:await asyncio.sleep(.21);v.finished[chat].set()
    v.calls.play.side_effect=play
    v.set_preset('gtts','mx');v.enqueue(-100,1,'hola','es')
    v.set_preset('macos');v.enqueue(-100,2,'hello','en')
    await v.workers[-100]
    assert v.tts.synthesize.call_args_list[0].kwargs=={'backend':'gtts','accent':'mx'}
    assert v.tts.synthesize.call_args_list[1].kwargs=={'backend':'macos','accent':'default'}

@pytest.mark.asyncio
async def test_paused_playback_resumes_and_tracks_pause_time(voice):
    v=voice;v.calls.pause=AsyncMock(return_value=True);v.calls.resume=AsyncMock(return_value=True)
    v.finished[-100]=asyncio.Event();v.pause_time[-100]=0
    await v.pause(-100);assert -100 in v.paused
    await asyncio.sleep(.01)
    await v.resume(-100);assert -100 not in v.paused
    assert v.pause_time[-100]>0

@pytest.mark.asyncio
async def test_stop_cancels_media_preparation_and_leaves(voice):
    from app.media import MediaItem
    v=voice;v.connected.add(-100);started=asyncio.Event();cancelled=asyncio.Event()
    async def prepare(item):
        started.set()
        try:await asyncio.Event().wait()
        finally:cancelled.set()
    v.media=SimpleNamespace(prepare=prepare)
    v.enqueue_media(-100,1,MediaItem('test',url='https://youtu.be/test'))
    await started.wait();await v.stop(-100)
    assert cancelled.is_set() and not v.connected
    assert v.storage.db.execute('SELECT status FROM voice_jobs').fetchone()[0]=='cancelled'
    v.tts.synthesize.assert_not_awaited()
