import httpx
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from app.hermes import Hermes,object_json
from app.config import Config

@pytest.mark.asyncio
async def test_retry_retains_memory_scope_and_auth(monkeypatch):
    h=Hermes(Config.load());seen=[]
    async def transport(request):
        seen.append(request.headers.get('X-Hermes-Session-Key'))
        if len(seen)==1:raise httpx.ConnectError('offline',request=request)
        return httpx.Response(200,json={'ok':True})
    await h.http.aclose();h.http=httpx.AsyncClient(base_url=h.config.base_url,transport=httpx.MockTransport(transport))
    async def no_wait(_):pass
    monkeypatch.setattr('app.hermes.asyncio.sleep',no_wait)
    try:
        await h.request('POST','/test',headers={'X-Hermes-Session-Key':'scope-1'},json={})
        assert seen==['scope-1','scope-1']
    finally:await h.close()

@pytest.mark.asyncio
async def test_ambiguous_read_timeout_never_retries():
    h=Hermes(Config.load());seen=[]
    def transport(request):
        seen.append(request)
        raise httpx.ReadTimeout('request may have completed',request=request)
    await h.http.aclose();h.http=httpx.AsyncClient(base_url=h.config.base_url,transport=httpx.MockTransport(transport))
    try:
        with pytest.raises(httpx.ReadTimeout):await h.request('POST','/test',json={})
        assert len(seen)==1
    finally:await h.close()

def test_internal_protocol_rejects_plain_text():
    assert object_json('```json\n{"text":"hi"}\n```')['text']=='hi'
    with pytest.raises(ValueError):object_json('["unsafe"]')

@pytest.mark.asyncio
async def test_translation_shortcut_without_source_is_actionable_not_error():
    h=Hermes(Config.load());h.classify=AsyncMock()
    try:
        answer=await h.answer(SimpleNamespace(translate=True,text='',language='zh',speak=False),None,1,0,None)
        assert 'responde' in answer.text.lower() or 'incluye' in answer.text.lower()
        assert answer.mode=='translation'
        assert answer.language=='es'
        h.classify.assert_not_awaited()
    finally:await h.close()
