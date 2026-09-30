import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from app.config import Config
from app.gateway import Gateway
from app.storage import Storage
from app.hermes import Answer

@pytest.fixture
def gateway(tmp_path):
    g=object.__new__(Gateway);g.config=Config.load();g.storage=Storage(tmp_path/'db')
    g.hermes=SimpleNamespace(translate=AsyncMock(return_value=Answer('hello','en',False,'translation')))
    g.client=SimpleNamespace(edit_message=AsyncMock(),send_message=AsyncMock(return_value=SimpleNamespace(id=8)))
    from collections import defaultdict
    g.reaction_locks=defaultdict(asyncio.Lock)
    yield g;g.storage.close()

@pytest.mark.asyncio
async def test_edit_only_own_recorded_messages(gateway):
    g=gateway;c=g.config.owner
    other=SimpleNamespace(id=1,sender_id=c)
    with pytest.raises(ValueError):await g.edit_translation(c,other,'en')
    g.client.edit_message.assert_not_awaited()
    mine=SimpleNamespace(id=2,sender_id=g.config.identity)
    with pytest.raises(ValueError):await g.edit_translation(c,mine,'en')
    g.storage.generated(c,2,'hola','es');await g.edit_translation(c,mine,'en')
    g.client.edit_message.assert_awaited_once()
    await g.edit_translation(c,mine,'en')
    assert g.client.edit_message.await_count==1 and g.hermes.translate.await_count==1

@pytest.mark.asyncio
async def test_edit_concurrency(gateway):
    g=gateway;c=g.config.owner;mine=SimpleNamespace(id=2,sender_id=g.config.identity)
    g.storage.generated(c,2,'hola','es')
    await asyncio.gather(g.edit_translation(c,mine,'en'),g.edit_translation(c,mine,'en'))
    assert g.hermes.translate.await_count==1
