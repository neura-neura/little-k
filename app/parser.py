import re
from dataclasses import dataclass

# Canonical syntax: .t <ISO language> .c <request>. Match standalone shortcuts only.
LANGS = frozenset('es en zh ja ko fr de pt it ru ar hi nl sv da no fi pl tr uk vi th id ms he el cs ro hu ca'.split())
TOKEN = re.compile(r'(?<!\S)\.(?:(?P<t>t)(?:\.(?P<dot>[a-z]{2,3})|(?P<short>[a-z]{2,3}))?|(?P<c>c))(?=\s|$)',re.I)
@dataclass(frozen=True)
class Request:
    text: str
    translate: bool = False
    language: str | None = None
    speak: bool = False


def parse(text):
    language, translate, speak = None, False, False
    parts=[];end=0
    for match in TOKEN.finditer(text):
        if match.start()<end: continue
        lang=match.group('dot') or match.group('short')
        if lang and lang.lower() not in LANGS: continue
        parts.append(text[end:match.start()]);end=match.end()
        if match.group('c'): speak=True
        else:
            translate=True
            if lang:language=lang.lower()
            else:
                next_lang=re.match(r'\s+([a-z]{2,3})(?=\s|$)',text[end:],re.I)
                if next_lang and next_lang[1].lower() in LANGS:
                    language=next_lang[1].lower();end+=next_lang.end()
    parts.append(text[end:])
    return Request(''.join(parts).strip(),translate,language,speak)


def topic_id(message):
    reply=getattr(message,'reply_to',None)
    if not reply or not getattr(reply,'forum_topic',False):return 0
    return getattr(reply,'reply_to_top_id',None) or getattr(reply,'reply_to_msg_id',None) or 0


def split_text(text, limit=4000):
    """Respect Telegram UTF-16 length and preserve every character."""
    while text:
        units=0;end=0
        for char in text:
            cost=2 if ord(char)>0xFFFF else 1
            if units+cost>limit:break
            units+=cost;end+=1
        if end==len(text):yield text;return
        prefix=text[:end]
        cut=prefix.rfind('\n\n')
        if cut<end//2:
            stops=list(re.finditer(r'[.!?。！？]\s',prefix));cut=stops[-1].end() if stops else -1
        if cut<end//2:cut=prefix.rfind(' ')+1
        if cut<end//2:cut=end
        yield text[:cut];text=text[cut:]
