import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
import httpx
from app.images import image_part,is_image
from app.config import Config
from app.hermes import Hermes

@pytest.mark.asyncio
async def test_photo_is_encoded_without_disk_file():
    message=SimpleNamespace(photo=True,file=SimpleNamespace(size=10))
    client=SimpleNamespace(download_media=AsyncMock(return_value=b'\xff\xd8\xfftest'))
    part=await image_part(client,message)
    assert part['image_url']['url'].startswith('data:image/jpeg;base64,')
    client.download_media.assert_awaited_once_with(message,file=bytes)

@pytest.mark.asyncio
async def test_oversize_image_not_downloaded():
    message=SimpleNamespace(photo=True,file=SimpleNamespace(size=6*1024*1024))
    client=SimpleNamespace(download_media=AsyncMock())
    with pytest.raises(ValueError):await image_part(client,message)
    client.download_media.assert_not_awaited()

@pytest.mark.asyncio
async def test_native_session_receives_image_parts():
    h=Hermes(Config.load());seen=[]
    async def transport(request):
        if request.method=='GET':return httpx.Response(200,json={'id':'test'})
        seen.append(json.loads(request.content));return httpx.Response(200,json={'message':{'content':'visible'}})
    await h.http.aclose();h.http=httpx.AsyncClient(base_url=h.config.base_url,transport=httpx.MockTransport(transport))
    part={'type':'image_url','image_url':{'url':'data:image/png;base64,AAAA'}}
    try:
        await h.turn('test','question','instructions',images=[part])
        assert seen[0]['message']==[{'type':'text','text':'question'},part]
    finally:await h.close()
