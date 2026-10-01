import asyncio
from collections import defaultdict
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from app.config import Config
from app.gateway import Gateway
from app.media import MediaItem
from app.playback import Playback, is_playback_request
from app.storage import Storage
from app.voice import Voice

@pytest.fixture
def playback(tmp_path):
    config=Config.load();storage=Storage(tmp_path/'state.db')
    voice=object.__new__(Voice);voice.storage=storage;voice.config=config
    voice.enqueue_media=__import__('unittest.mock',fromlist=['Mock']).Mock()
    voice.stop=AsyncMock();voice.on_media_done=None
    g=SimpleNamespace(config=config,voice=voice,send=AsyncMock())
    p=Playback(g)
    yield p
    storage.close()


def event(p,text,sender=None,private=False):
    cfg=p.gateway.config
    return SimpleNamespace(raw_text=text,sender_id=sender or cfg.owner,
                           chat_id=cfg.owner if private else next(iter(cfg.chats)),
                           id=50,is_private=private)

@pytest.mark.asyncio
async def test_voice_preset_persists_and_owner_only(playback,tmp_path):
    p=playback
    await p.handle(event(p,'.voice gtts'))
    assert p.gateway.voice.preset()=={'backend':'gtts','accent':'default'}
    await p.handle(event(p,'.voice macos',sender=4444))
    assert p.gateway.voice.preset()['backend']=='gtts'
    assert 'Only the owner' in p.gateway.send.call_args.args[1]
    reopened=Storage(tmp_path/'state.db',recover=False)
    assert reopened.setting('voice_profile')['backend']=='gtts'
    reopened.close()
    await p.handle(event(p,'.voice macos'))
    assert p.gateway.voice.preset()['backend']=='macos'

@pytest.mark.asyncio
async def test_invalid_voice_does_not_change_saved_preset(playback):
    p=playback;await p.handle(event(p,'.voice gtts unsupported'))
    assert p.gateway.voice.preset()['backend']=='macos'

@pytest.mark.asyncio
async def test_media_queue_private_denial_and_reply(playback):
    p=playback
    await p.handle(event(p,'.play https://youtu.be/test',private=True))
    p.gateway.voice.enqueue_media.assert_not_called()
    await p.handle(event(p,'.play'),SimpleNamespace(raw_text='https://youtu.be/test'))
    assert p.gateway.voice.enqueue_media.call_args.args[2].url=='https://youtu.be/test'

@pytest.mark.asyncio
async def test_spotify_selection_is_requester_scoped(playback):
    p=playback
    p.gateway.voice.media=SimpleNamespace(spotify_query=AsyncMock(return_value='Artist Song'),
        netease=SimpleNamespace(search=AsyncMock(return_value=[{'kind':'song','id':123,'name':'Song'}]),
                               content=AsyncMock(return_value={'name':'Song','songs':[{'id':123,'name':'Song'}]})))
    await p.handle(event(p,'.play https://open.spotify.com/track/abc'))
    await p.handle(event(p,'.pick 1',sender=4444))
    p.gateway.voice.enqueue_media.assert_not_called()
    await p.handle(event(p,'.pick 1'))
    assert p.gateway.voice.enqueue_media.call_args.args[2].song['id']==123

@pytest.mark.asyncio
async def test_collection_advance_rejects_stale_callbacks(playback):
    p=playback;chat=next(iter(p.gateway.config.chats))
    items=[MediaItem('one',song={'id':1}),MediaItem('two',song={'id':2})]
    p.start_collection(chat,50,'album',items)
    state=p.collections[chat]
    old=SimpleNamespace(chat=chat,collection='old',index=0)
    await p.finished(old,True)
    assert state.index==0
    job=SimpleNamespace(chat=chat,collection=state.token,index=0)
    await p.finished(job,True)
    assert state.index==1 and p.gateway.voice.enqueue_media.call_args.args[2]==items[1]
    p.cancel_collection(chat)
    await p.finished(SimpleNamespace(chat=chat,collection=state.token,index=1),True)
    assert chat not in p.collections

@pytest.mark.asyncio
async def test_media_routes_without_mention_or_hermes(tmp_path):
    g=object.__new__(Gateway);g.config=Config.load();g.ready=True;g.username=None;g.tasks=set()
    g.locks=defaultdict(asyncio.Lock);g.storage=Storage(tmp_path/'state.db')
    g.playback=SimpleNamespace(handle=AsyncMock(return_value=True))
    g.hermes=SimpleNamespace(classify=AsyncMock(),answer=AsyncMock())
    e=SimpleNamespace(chat_id=next(iter(g.config.chats)),sender_id=5555,is_private=False,out=False,
                      raw_text='.play https://youtu.be/test',id=11,is_reply=False,mentioned=False,
                      message=SimpleNamespace(reply_to=None))
    try:
        await g.on_message(e);await asyncio.gather(*list(g.tasks))
        g.playback.handle.assert_awaited_once();g.hermes.classify.assert_not_awaited()
        await g.on_message(e)
        assert g.playback.handle.await_count==1
    finally:g.storage.close()

@pytest.mark.parametrize('text',['.PLAY https://youtu.be/abc','.voice','.pause','https://music.163.com/song?id=123'])
def test_explicit_commands(text):assert is_playback_request(text)

@pytest.mark.parametrize('text',['Discuss https://youtu.be/abc','https://youtube.com.evil.example/a','.playlist'])
def test_regular_messages_not_intercepted(text):assert not is_playback_request(text)
