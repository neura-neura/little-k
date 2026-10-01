import asyncio
import logging
import time
from collections import defaultdict
from telethon import TelegramClient, events, errors, types
from .config import Config
from .parser import parse, split_text, topic_id
from .storage import Storage
from .hermes import Hermes
from .voice import Voice
from .help import is_help_command, help_text
from .playback import Playback, is_playback_request

log=logging.getLogger(__name__)
def detect_language(text):
    from langdetect import detect,DetectorFactory
    DetectorFactory.seed=0
    try:
        lang=detect(text).split('-')[0]
        return lang if lang in Config.load().voices else 'es'
    except Exception:return 'es'

FLAGS={'en':'🇬🇧','zh':'🇨🇳','es':'🇲🇽','ja':'🇯🇵','ko':'🇰🇷','fr':'🇫🇷','de':'🇩🇪','pt':'🇵🇹','it':'🇮🇹'}
class Gateway:
    def __init__(self,config):
        self.config=config;self.storage=Storage(config.db);self.hermes=Hermes(config)
        config.session.chmod(0o600)
        self.client=TelegramClient(str(config.session),config.api_id,config.api_hash,
                                   auto_reconnect=True,connection_retries=10,retry_delay=5,flood_sleep_threshold=0)
        self.locks=defaultdict(asyncio.Lock);self.reaction_locks=defaultdict(asyncio.Lock)
        self.tasks=set();self.last_request={};self.username=None;self.ready=False
        self.voice=Voice(self.client,config,self.storage,self.send)
        self.playback=Playback(self);self.diagnostics=None;self.closed=False
        self.client.add_event_handler(self.on_message,events.NewMessage(incoming=True))
        self.client.add_event_handler(self.on_reaction,events.Raw(types.UpdateMessageReactions))
    async def telegram(self,fn,*args,**kwargs):
        for attempt in range(3):
            try:return await fn(*args,**kwargs)
            except errors.FloodWaitError as exc:
                log.warning('Telegram FloodWait seconds=%s',exc.seconds)
                if exc.seconds>300 or attempt==2:raise
                await asyncio.sleep(exc.seconds+1)
            except (errors.ServerError,ConnectionError):
                if attempt==2:raise
                await asyncio.sleep(2**attempt)
    async def send(self,chat,text,reply=None,language='es'):
        sent=[]
        # Plain text is the guaranteed safe format; never fail on Markdown entities.
        for part in split_text(text):
            m=await self.telegram(self.client.send_message,chat,part,reply_to=reply,parse_mode=None,link_preview=False)
            self.storage.generated(chat,m.id,part,language);sent.append(m)
        return sent
    async def on_message(self,event):
        if not self.ready:return
        if not self.config.allowed(event.chat_id,event.sender_id,event.is_private,event.out):return
        help_requested=is_help_command(event.raw_text)
        playback_requested=is_playback_request(event.raw_text)
        request=parse(event.raw_text or '')
        if not request.text and not (request.translate or request.speak):return
        reply=await event.get_reply_message() if event.is_reply else None
        mentioned=event.mentioned or (self.username and '@'+self.username.lower() in event.raw_text.lower())
        addressed=event.raw_text.lower().startswith(('little k','littlek','@littlek'))
        # Owner can use natural language in allowlisted groups; others must explicitly address K.
        if not event.is_private and not (help_requested or playback_requested or mentioned or addressed or request.translate or request.speak or
            (reply and reply.sender_id==self.config.identity) or event.sender_id==self.config.owner or event.raw_text.lower().startswith('/k ')):return
        event._littlek_route_only = not event.is_private and not (mentioned or addressed or
                request.translate or request.speak or (reply and reply.sender_id==self.config.identity)
                or event.raw_text.lower().startswith(('k,','/k ')))
        key=f'message:{event.chat_id}:{event.id}'
        if not self.storage.claim(key):return
        task=asyncio.create_task(self.process(event,request,reply,key));self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
    async def process(self,event,request,reply,key):
        chat=event.chat_id;topic=topic_id(event.message);start=time.monotonic()
        async with self.locks[(chat,topic)]:
            try:
                if is_help_command(event.raw_text):
                    await self.send(chat,help_text(event.sender_id==self.config.owner),event.id,language='en')
                    self.storage.finish(key);return
                if is_playback_request(event.raw_text) and await self.playback.handle(event,reply):
                    self.storage.finish(key);return
                if await self.admin(event,topic):self.storage.finish(key);return
                now=time.monotonic();previous=self.last_request.get(event.sender_id,0)
                if now-previous<1.5:await asyncio.sleep(1.5-(now-previous))
                self.last_request[event.sender_id]=time.monotonic()
                intent=None
                if getattr(event,'_littlek_route_only',False):
                    intent=await self.hermes.classify(request,reply.raw_text if reply else None)
                    # Only explicit operations directed at this gateway activate an unaddressed group turn.
                    if not intent['speak'] and intent['mode']!='translation':
                        self.storage.finish(key,'ignored');return
                async with self.client.action(chat,'typing'):
                    if request.translate and not request.text and reply and self.storage.message(chat,reply.id):
                        answer=await self.edit_translation(chat,reply,request.language)
                        if request.speak:self.voice.enqueue(chat,reply.id,answer.text,answer.language)
                    else:
                        # Deterministic .c-only reply: read the referenced answer/text, do not answer it again.
                        if request.speak and not request.text and not request.translate and reply:
                            from .hermes import Answer
                            record=self.storage.message(chat,reply.id)
                            answer=Answer(reply.raw_text,record['language'] if record else detect_language(reply.raw_text),True)
                        else:
                            answer=await self.hermes.answer(request,reply.raw_text if reply else None,chat,topic,self.storage,intent=intent)
                        sent=await self.send(chat,answer.text,event.id,answer.language)
                        if answer.speak:
                            try:self.voice.enqueue(chat,sent[0].id,answer.text,answer.language)
                            except Exception:await self.send(chat,'necesito una llamada activa en un grupo permitido 🐈',event.id)
                self.storage.finish(key);self.storage.prune()
                log.info('Request completed chat=%s topic=%s elapsed=%.1fs',chat,topic,time.monotonic()-start)
            except asyncio.CancelledError:self.storage.finish(key,'interrupted');raise
            except Exception as exc:
                self.storage.finish(key,'failed')
                log.error('Request failed chat=%s type=%s',chat,type(exc).__name__)
                try:await self.send(chat,'mmm... algo salió mal allá atrás 🐈',event.id)
                except Exception:log.warning('Error notification failed')
    async def edit_translation(self,chat,reply,language):
        if reply.sender_id!=self.config.identity:raise ValueError('Cannot edit another identity')
        async with self.reaction_locks[(chat,reply.id)]:
            record=self.storage.message(chat,reply.id)
            if not record:raise ValueError('Message not generated by gateway')
            from .hermes import Answer
            if language and language in record['translations']:
                return Answer(record['translations'][language],language,False,'translation')
            answer=await self.hermes.translate(record['original'],language)
            if answer.language in record['translations']:
                return Answer(record['translations'][answer.language],answer.language,False,'translation')
            translations={**record['translations'],answer.language:answer.text}
            rendered=record['original']+'\n──────────\n'+'\n'.join(FLAGS.get(lang,lang)+' '+text for lang,text in translations.items())
            if len(rendered.encode('utf-16-le'))//2<=4096:
                try:await self.telegram(self.client.edit_message,chat,reply.id,rendered,parse_mode=None)
                except errors.MessageNotModifiedError:pass
                except (errors.MessageEditTimeExpiredError,errors.MessageAuthorRequiredError):
                    await self.send(chat,answer.text,reply.id,answer.language)
            else:await self.send(chat,answer.text,reply.id,answer.language)
            self.storage.translation(chat,reply.id,answer.language,answer.text)
            return answer
    async def on_reaction(self,update):
        if not self.ready:return
        chat=__import__('telethon').utils.get_peer_id(update.peer)
        record=self.storage.message(chat,update.msg_id)
        if not record:return
        for item in update.reactions.recent_reactions or []:
            sender=__import__('telethon').utils.get_peer_id(item.peer_id)
            if not self.config.allowed(chat,sender,chat>0):continue
            # Group reaction updates do not always identify all reactors. Never infer missing identity.
            emoji=getattr(item.reaction,'emoticon',None)
            language={'🇬🇧':'en','🇨🇳':'zh'}.get(emoji)
            if not language:continue
            key=f'reaction:{chat}:{update.msg_id}:{sender}:{language}'
            if not self.storage.claim(key):continue
            async def handle(chat=chat,mid=update.msg_id,lang=language,key=key):
                try:
                    message=await self.client.get_messages(chat,ids=mid)
                    await self.edit_translation(chat,message,lang);self.storage.finish(key)
                except Exception as exc:
                    self.storage.finish(key,'failed');log.warning('Reaction failed type=%s',type(exc).__name__)
            task=asyncio.create_task(handle());self.tasks.add(task);task.add_done_callback(self.tasks.discard)
    async def admin(self,event,topic):
        raw=(event.raw_text or '').strip().lower()
        if not raw.startswith('/k '):return False
        if event.sender_id!=self.config.owner:
            await self.send(event.chat_id,'eso sólo lo puede pedir mi humano 🐈',event.id);return True
        cmd=raw[3:];chat=event.chat_id
        if cmd=='status':
            try:await self.hermes.health();hermes='OK'
            except Exception:hermes='unavailable'
            text=f'Little K · Telegram OK · Hermes {hermes} · voz {self.voice.status(chat)}'
        elif cmd=='new':self.storage.reset(chat,topic);text='conversación nueva 🐾'
        elif cmd=='voice status':text=str(self.voice.status(chat))
        elif cmd=='voice stop':
            self.playback.cancel_collection(chat);await self.voice.stop(chat);text='ya me callé 🐈'
        elif cmd=='voice clear':
            self.playback.cancel_collection(chat);text=f'cola vaciada: {self.voice.clear(chat)}'
        elif cmd=='reload':
            cfg=Config.load()
            if (cfg.identity,cfg.owner,cfg.api_id,cfg.session)!=(self.config.identity,self.config.owner,self.config.api_id,self.config.session):
                text='para cambiar identidad o credenciales, reinicia el servicio'
            else:
                self.config=cfg;self.hermes.config=cfg;self.voice.config=cfg;self.voice.tts.config=cfg;self.voice.media.config=cfg;
                self.voice.media.netease.cookie_path=cfg.netease_cookies;self.voice.media.netease.max_tracks=cfg.media_max_tracks;text='configuración recargada 🐾'
        else:text='/k status · new · voice status · voice stop · voice clear · reload'
        await self.send(chat,text,event.id);return True
    async def monitor(self):
        ready=False;waiting_logged=False
        while True:
            try:
                await self.hermes.health()
                if not ready:log.info('Hermes connected; native bot Little K found');ready=True;waiting_logged=False
            except Exception as exc:
                if ready:log.warning('Hermes temporarily unavailable type=%s',type(exc).__name__)
                ready=False
                if not waiting_logged:log.info('Waiting for Hermes startup; retrying automatically');waiting_logged=True
            await asyncio.sleep(20)
    async def run(self,stop):
        await self.client.connect()
        if not await self.client.is_user_authorized():raise ValueError('Authorize dedicated Telegram account separately')
        me=await self.client.get_me()
        if me.id!=self.config.identity or me.id==self.config.owner or me.bot:
            raise ValueError('Session identity mismatch: refusing to start')
        self.username=me.username;self.ready=True
        from .diagnostics import Diagnostics
        diagnostics=Diagnostics(self);self.diagnostics=diagnostics;await diagnostics.start()
        log.info('Telegram MTProto connected; Little K identity verified id=%s owner=%s',me.id,self.config.owner)
        try:await self.voice.start()
        except Exception as exc:log.warning('Voice initialization failed type=%s; will retry on request',type(exc).__name__)
        await self.client.catch_up()
        monitor=asyncio.create_task(self.monitor());disconnected=asyncio.create_task(self.client.run_until_disconnected());stopper=asyncio.create_task(stop.wait())
        try:
            await asyncio.wait([disconnected,stopper],return_when=asyncio.FIRST_COMPLETED)
        finally:
            monitor.cancel();stopper.cancel();disconnected.cancel()
            await asyncio.gather(monitor,stopper,disconnected,return_exceptions=True)
            await self.close()
    async def close(self):
        if self.closed:return
        self.closed=True;self.ready=False
        for task in list(self.tasks):task.cancel()
        await asyncio.gather(*list(self.tasks),return_exceptions=True)
        # Release every resource even when an earlier close operation fails.
        callbacks=[]
        if self.diagnostics:callbacks.append(self.diagnostics.close)
        callbacks.extend((self.voice.close,self.client.disconnect,self.hermes.close))
        failed=False
        for close in callbacks:
            try:await close()
            except Exception as exc:
                failed=True;log.error('Shutdown step failed type=%s',type(exc).__name__)
        self.storage.close()
        log.info('Gateway shutdown completed clean=%s',not failed)
