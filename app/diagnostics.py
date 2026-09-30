"""Diagnostics and explicitly invoked local voice test over a private Unix socket."""
import asyncio
import json
import os
from telethon import functions, types
from .config import ROOT

class Diagnostics:
    def __init__(self,gateway):self.gateway=gateway;self.path=ROOT/'data/control.sock';self.server=None
    async def start(self):
        self.path.unlink(missing_ok=True)
        self.server=await asyncio.start_unix_server(self.handle,path=str(self.path));self.path.chmod(0o600)
    async def handle(self,reader,writer):
        try:
            raw=await asyncio.wait_for(reader.readline(),5)
            if len(raw)>1024:raise ValueError('Invalid request')
            request=json.loads(raw);g=self.gateway
            if request.get('command')=='status':
                result={'pid':os.getpid(),'telegram_connected':g.client.is_connected(),
                        'identity_verified':g.ready,'identity':g.config.identity,'owner_distinct':g.config.identity!=g.config.owner,
                        'voice_library_started':g.voice.started,'active_requests':len(g.tasks),
                        'voice':{str(chat):g.voice.status(chat) for chat in g.voice.queues}}
            elif request.get('command')=='voice_smoke':
                chat=int(request.get('chat',0));language=request.get('language','es')
                if chat not in g.config.chats or language not in g.config.voices:raise ValueError('Test requires allowed group and configured language')
                # Explicitly invoked by the local operator; never replay incoming messages.
                raw=await g.hermes.auxiliary('Preséntate con tu personalidad en una frase corta para una prueba de audio. Idioma: '+language,
                                           'Sólo una frase con tu personalidad de SOUL.md. No uses herramientas ni guardes memorias.')
                answer=await g.hermes.decode_answer(raw)
                messages=await g.send(chat,answer['text'],language=language)
                g.voice.enqueue(chat,messages[0].id,answer['text'],language)
                result={'queued':True,'chat':chat,'language':language}
            elif request.get('command')=='probe_chats':
                chats=[]
                for chat in g.config.chats:
                    try:
                        entity=await g.client.get_entity(chat)
                        if isinstance(entity,types.Channel):
                            full=await g.client(functions.channels.GetFullChannelRequest(entity))
                        else:full=await g.client(functions.messages.GetFullChatRequest(entity.id))
                        call=getattr(full.full_chat,'call',None)
                        info={'chat':chat,'active_call':call is not None}
                        if call:
                            people=await g.client(functions.phone.GetGroupParticipantsRequest(call,ids=[await g.client.get_input_entity('me')],sources=[],offset='',limit=10))
                            from telethon.utils import get_peer_id
                            own=next((p for p in people.participants if get_peer_id(p.peer)==g.config.identity),None)
                            info.update(little_k_in_call=own is not None)
                            if own:info.update(muted=own.muted,can_self_unmute=own.can_self_unmute,volume=own.volume)
                        chats.append(info)
                    except Exception as exc:chats.append({'chat':chat,'error':type(exc).__name__})
                result={'chats':chats}
            else:result={'error':'Unknown read-only command'}
            writer.write((json.dumps(result)+'\n').encode());await writer.drain()
        except Exception as exc:
            writer.write((json.dumps({'error':type(exc).__name__})+'\n').encode())
        finally:writer.close();await writer.wait_closed()
    async def close(self):
        if self.server:self.server.close();await self.server.wait_closed()
        self.path.unlink(missing_ok=True)

async def query(command='status',**kwargs):
    reader,writer=await asyncio.open_unix_connection(str(ROOT/'data/control.sock'))
    try:
        writer.write((json.dumps({'command':command,**kwargs})+'\n').encode());await writer.drain()
        return json.loads(await asyncio.wait_for(reader.readline(),180))
    finally:writer.close();await writer.wait_closed()
