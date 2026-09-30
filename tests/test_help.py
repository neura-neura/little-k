import asyncio
from collections import defaultdict
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from app.config import Config
from app.gateway import Gateway
from app.help import help_text, is_help_command
from app.storage import Storage


@pytest.mark.parametrize('text',['.h','.H','  .h\n'])
def test_help_command(text):
    assert is_help_command(text)


@pytest.mark.parametrize('text',['.hello','This is .h','.h more','.h.c',''])
def test_help_not_regular_text(text):
    assert not is_help_command(text)


def test_help_matches_role():
    public=help_text();owner=help_text(owner=True)
    assert '.t [language]' in public and '.c [request]' in public
    assert '/k status' not in public
    for command in ['/k status','/k new','/k voice status','/k voice stop','/k voice clear','/k reload']:
        assert command in owner
    assert 'current playback continues' in owner
    assert 'Show this command reference in English' in public


@pytest.mark.asyncio
@pytest.mark.parametrize('private,owner',[(False,False),(False,True),(True,False),(True,True)])
async def test_help_routed_without_mention_or_hermes(tmp_path,private,owner):
    g=object.__new__(Gateway);config=Config.load()
    sender=config.owner if owner else 55555
    g.config=replace(config,private_users=frozenset({sender}))
    chat=sender if private else next(iter(config.chats))
    g.ready=True;g.username=None;g.tasks=set();g.locks=defaultdict(asyncio.Lock)
    g.storage=Storage(tmp_path/'state.db');g.send=AsyncMock()
    g.hermes=SimpleNamespace(classify=AsyncMock(side_effect=RuntimeError('Hermes offline')),
                             answer=AsyncMock(side_effect=RuntimeError('Hermes offline')))
    event=SimpleNamespace(chat_id=chat,sender_id=sender,is_private=private,out=False,
                          raw_text='.H',id=51,is_reply=False,mentioned=False,
                          message=SimpleNamespace(reply_to=None))
    try:
        await g.on_message(event)
        await asyncio.gather(*list(g.tasks))
        g.send.assert_awaited_once_with(chat,help_text(owner),51,language='en')
        g.hermes.classify.assert_not_awaited();g.hermes.answer.assert_not_awaited()
        await g.on_message(event)
        assert g.send.await_count==1  # duplicate Telegram update does not repeat help
    finally:g.storage.close()


@pytest.mark.asyncio
async def test_help_respects_allowlist(tmp_path):
    g=object.__new__(Gateway);g.ready=True;g.config=Config.load();g.send=AsyncMock()
    event=SimpleNamespace(chat_id=-99999,sender_id=g.config.owner,is_private=False,out=False,raw_text='.h')
    await g.on_message(event)
    g.send.assert_not_awaited()
