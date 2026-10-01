"""Explicit Telegram commands; no Hermes request is needed for media or voices."""
import asyncio
from dataclasses import dataclass
import time
import uuid
from .media import MediaItem, bare_url, platform

COMMANDS={'.voice','.play','.pick','.pause','.resume','.stop','.next','.previous','.queue'}


def command(text):
    text=(text or '').strip()
    return text.split(maxsplit=1)[0].lower() if text else ''


def is_playback_request(text):
    return command(text) in COMMANDS or bool(bare_url(text))


@dataclass
class Collection:
    token:str
    title:str
    items:list
    index:int
    message:int


class Playback:
    def __init__(self,gateway):
        self.gateway=gateway;self.collections={};self.selections={}
        self.locks={}
        gateway.voice.on_media_done=self.finished

    def cancel_collection(self,chat):
        self.collections.pop(chat,None)
        for key in list(self.selections):
            if key[0]==chat:self.selections.pop(key,None)

    async def handle(self,event,reply=None):
        raw=(event.raw_text or '').strip();cmd=command(raw)
        if not is_playback_request(raw):return False
        g=self.gateway;chat=event.chat_id;parts=raw.split(maxsplit=1)
        args=parts[1].strip() if len(parts)>1 else ''
        try:
            if cmd=='.voice':
                if args and args.lower() not in ('status','list'):
                    if event.sender_id!=g.config.owner:
                        await g.send(chat,'Only the owner can change the global voice preset.',event.id);return True
                    values=args.lower().split()
                    if len(values)>2:raise ValueError('Use .voice macos or .voice gtts [accent].')
                    backend=values[0];accent=values[1] if len(values)>1 else 'default'
                    aliases={'local':'macos','legacy':'gtts','google':'gtts'}
                    g.voice.set_preset(aliases.get(backend,backend),accent)
                preset=g.voice.preset()
                await g.send(chat,f"Voice: {preset['backend']} / {preset['accent']}. Saved across restarts.\n"
                    'Switch: .voice macos · .voice gtts\n'
                    'gTTS accents: default (old bot), mx, es, uk, au, ie, in.\n'
                    'The choice is global and applies to newly queued speech. gTTS sends speech text to Google.',event.id,language='en')
                return True
            if event.is_private:raise ValueError('Media playback requires an allowed group with an active voice chat.')
            lock=self.locks.setdefault(chat,asyncio.Lock())
            async with lock:
                if cmd=='.queue':
                    state=g.voice.status(chat);collection=self.collections.get(chat)
                    text=f"Playback: {state}"
                    if collection:text+=f'\nCollection: {collection.title} ({collection.index+1}/{len(collection.items)})'
                    await g.send(chat,text,event.id,language='en')
                elif cmd=='.pause':await g.voice.pause(chat);await g.send(chat,'Playback paused.',event.id,language='en')
                elif cmd=='.resume':await g.voice.resume(chat);await g.send(chat,'Playback resumed.',event.id,language='en')
                elif cmd=='.stop':
                    self.cancel_collection(chat);await g.voice.stop(chat)
                    await g.send(chat,'Playback stopped, queue cleared and call left.',event.id,language='en')
                elif cmd in ('.next','.previous'):
                    state=self.collections.get(chat)
                    if state:
                        index=state.index+(1 if cmd=='.next' else -1)
                        if not 0<=index<len(state.items):raise ValueError('There are no more tracks in that direction.')
                        # Invalidate first: a stream ending during stop cannot advance the old collection.
                        self.collections.pop(chat,None);await g.voice.stop(chat)
                        self.start_collection(chat,event.id,state.title,state.items,index)
                        await g.send(chat,f'Queued track {index+1}/{len(state.items)}.',event.id,language='en')
                    elif cmd=='.next':
                        # Skip current standalone item and keep the remaining queue.
                        queue=g.voice.queues.get(chat);pending=[]
                        if queue:
                            while not queue.empty():
                                job=queue.get_nowait();queue.task_done();pending.append(job)
                        await g.voice.stop(chat)
                        for job in pending:g.voice._enqueue(job)
                        await g.send(chat,'Skipped the current audio.',event.id,language='en')
                    else:raise ValueError('There is no active album or playlist.')
                elif cmd=='.pick':await self.pick(event,args)
                else:
                    url=raw if bare_url(raw) else args or (reply.raw_text if reply else '')
                    if not bare_url(url):raise ValueError('Use .play <YouTube|Bilibili|NetEase|Spotify URL>, or reply to a link with .play.')
                    await self.play(event,url)
            return True
        except (ValueError,asyncio.QueueFull) as exc:
            message=str(exc) if isinstance(exc,ValueError) else 'The audio queue is full. Use .queue or .stop.'
            await g.send(chat,message,event.id,language='en');return True
        except Exception as exc:
            # Service responses/exception text may contain signed URLs or cookies.
            import logging
            logging.getLogger(__name__).warning('Media command failed type=%s',type(exc).__name__)
            await g.send(chat,'Could not prepare this media. Check the URL, cookies and source availability.',event.id,language='en')
            return True

    def start_collection(self,chat,message,title,items,index=0):
        state=Collection(uuid.uuid4().hex,title,items,index,message)
        self.collections[chat]=state
        try:self.gateway.voice.enqueue_media(chat,message,items[index],state.token,index)
        except BaseException:self.collections.pop(chat,None);raise

    async def play(self,event,url):
        g=self.gateway;chat=event.chat_id;source=platform(url)
        if not g.config.voice_enabled:raise ValueError('Voice is disabled.')
        if source in ('youtube','bilibili'):
            self.collections.pop(chat,None)
            g.voice.enqueue_media(chat,event.id,MediaItem(source.title()+' audio',url=url))
            await g.send(chat,'Media queued. I will join the existing call and download the audio.',event.id,language='en')
        elif source=='netease':
            await g.send(chat,'Reading the NetEase collection…',event.id,language='en')
            content=await g.voice.media.netease.content(url)
            items=[MediaItem(song.get('artists','')+' — '+song['name'],song=song) for song in content['songs']]
            if not items:raise ValueError('This NetEase link contains no available tracks.')
            self.collections.pop(chat,None);await g.voice.stop(chat)
            self.start_collection(chat,event.id,content['name'],items)
            await g.send(chat,f"Queued {content['name']}: {len(items)} tracks. Use .next, .previous or .stop.",event.id,language='en')
        else:
            await g.send(chat,'Reading Spotify metadata and searching NetEase matches…',event.id,language='en')
            query=await g.voice.media.spotify_query(url)
            rows=await g.voice.media.netease.search(query)
            if not rows:raise ValueError('No matching NetEase results were found for this Spotify link.')
            self.selections[(chat,event.sender_id)]=(time.monotonic()+300,rows)
            text='Spotify → NetEase matches for '+query+'\n'
            text+='\n'.join(f"{i}. {row['kind']}: {row['name']} — {row.get('artists','')}" for i,row in enumerate(rows,1))
            text+='\nUse .pick <number> within 5 minutes; .pick 0 cancels. Audio comes from NetEase.'
            await g.send(chat,text,event.id,language='en')

    async def pick(self,event,args):
        key=(event.chat_id,event.sender_id);pending=self.selections.get(key)
        if not pending or pending[0]<time.monotonic():
            self.selections.pop(key,None);raise ValueError('No active selection. Send the Spotify link again.')
        if not args.isdigit():raise ValueError('Use .pick <number>, or .pick 0 to cancel.')
        index=int(args)
        if index==0:
            self.selections.pop(key,None);await self.gateway.send(event.chat_id,'Selection canceled.',event.id,language='en');return
        rows=pending[1]
        if not 1<=index<=len(rows):raise ValueError('Choose a number shown in your selection.')
        row=rows[index-1]
        await self.play(event,f"https://music.163.com/{row['kind']}?id={row['id']}")
        self.selections.pop(key,None)

    async def finished(self,job,completed):
        # Runs in the voice worker. Never wait for a command lock: .stop waits for
        # this worker, so doing so would deadlock. No awaits during state/enqueue.
        state=self.collections.get(job.chat)
        if not state or state.token!=job.collection or state.index!=job.index:return
        if completed and state.index+1<len(state.items):
            state.index+=1
            self.gateway.voice.enqueue_media(job.chat,state.message,state.items[state.index],state.token,state.index)
        else:self.collections.pop(job.chat,None)
