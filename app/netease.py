"""NetEase protocol adapted from the user-owned tgcall-tts-userbot."""

import base64
import json
import urllib.parse
from hashlib import md5
from secrets import choice
from random import randrange
from typing import Dict, Tuple
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

MODULUS = "00e0b509f6259df8642dbc35662901477df22677ec152b5ff68ace615bb7b725152b3ab17a876aea8a5aa76d2e417629ec4ee341f56135fccf695280104e0312ecbda92557c93870114af6c9d05c4f7f0c3685b7a46bee255932575cce10b424d813cfe4875d3e82047b97ddef52741d546b8e289dc6935b3ece0462db0a22b8e7"

PUBKEY = "010001"

NONCE = "0CoJUm6Qyw8W8jud"

IV = b"0102030405060708"

def create_secret_key(size: int = 16) -> str:
    return "".join(choice("0123456789abcdef") for _ in range(size))

def aes_encrypt(text: str, key: str) -> str:
    padder = padding.PKCS7(algorithms.AES.block_size).padder()
    padded = padder.update(text.encode("utf-8")) + padder.finalize()
    cipher = Cipher(algorithms.AES(key.encode("utf-8")), modes.CBC(IV))
    encryptor = cipher.encryptor()
    return base64.b64encode(encryptor.update(padded) + encryptor.finalize()).decode("utf-8")

def rsa_encrypt(text: str, pubkey: str, modulus: str) -> str:
    reversed_text = text[::-1]
    encrypted = pow(
        int(reversed_text.encode("utf-8").hex(), 16),
        int(pubkey, 16),
        int(modulus, 16),
    )
    return format(encrypted, "x").zfill(256)

def weapi_encrypt(payload: dict) -> Dict[str, str]:
    data = json.dumps(payload)
    secret_key = create_secret_key(16)
    params = aes_encrypt(aes_encrypt(data, NONCE), secret_key)
    enc_sec_key = rsa_encrypt(secret_key, PUBKEY, MODULUS)
    return {"params": params, "encSecKey": enc_sec_key}

def hash_hex_digest(text: str) -> str:
    return "".join(hex(value)[2:].zfill(2) for value in md5(text.encode("utf-8")).digest())

def song_url_payload(song_id: str, level: str = "exhigh") -> str:
    url = "https://interface3.music.163.com/eapi/song/enhance/player/url/v1"
    aes_key = b"e82ckenh8dichen8"
    config = {
        "os": "pc",
        "appver": "2.10.2.200154",
        "osver": "",
        "deviceId": "pyncm!",
        "requestId": str(randrange(20000000, 30000000)),
    }
    encode_type = "mp3" if level in {"standard", "exhigh"} else "flac"
    payload = {
        "ids": [int(song_id)],
        "level": level,
        "encodeType": encode_type,
        "header": json.dumps(config),
    }

    url2 = urllib.parse.urlparse(url).path.replace("/eapi/", "/api/")
    digest = hash_hex_digest(f"nobody{url2}use{json.dumps(payload)}md5forencrypt")
    params = f"{url2}-36cd479b6b5-{json.dumps(payload)}-36cd479b6b5-{digest}"

    padder = padding.PKCS7(algorithms.AES(aes_key).block_size).padder()
    padded_data = padder.update(params.encode()) + padder.finalize()
    cipher = Cipher(algorithms.AES(aes_key), modes.ECB())
    encryptor = cipher.encryptor()
    encrypted = encryptor.update(padded_data) + encryptor.finalize()
    encrypted_params = "".join(hex(value)[2:].zfill(2) for value in encrypted)
    return encrypted_params

def extract_type_and_id(url: str) -> Tuple[str, str]:
    parsed = urllib.parse.urlparse(url)

    if parsed.fragment:
        fragment = parsed.fragment[1:] if parsed.fragment.startswith("/") else parsed.fragment
        parts = fragment.split("?")
        subpath = parts[0]
        subquery = urllib.parse.parse_qs(parts[1]) if len(parts) > 1 else {}
        type_ = subpath.lower()
        if "id" in subquery:
            return type_, subquery["id"][0]
        path_parts = subpath.split("/")
        if len(path_parts) > 1:
            return path_parts[0].lower(), path_parts[1]
    else:
        subpath = parsed.path.strip("/").lower()
        type_ = subpath.split("/")[0] if "/" in subpath else subpath
        query = urllib.parse.parse_qs(parsed.query)
        if "id" in query:
            return type_, query["id"][0]
        if "/" in subpath:
            return type_, subpath.split("/")[1]

    raise ValueError("Unrecognized music.163.com URL.")


class NetEase:
    def __init__(self,http,cookie_path,max_tracks=100):
        self.http=http;self.cookie_path=cookie_path;self.max_tracks=max_tracks

    def cookies(self):
        if not self.cookie_path or not self.cookie_path.is_file():
            raise ValueError('NetEase cookies are missing; configure NETEASE_COOKIES_PATH.')
        data=json.loads(self.cookie_path.read_text(encoding='utf-8'))
        if isinstance(data,list):
            return {x['name']:x['value'] for x in data if isinstance(x,dict)
                    and 'name' in x and 'value' in x
                    and ((x.get('domain') or 'music.163.com').lstrip('.')=='music.163.com' or (x.get('domain') or '').endswith('.music.163.com'))}
        if isinstance(data,dict):return {k:v for k,v in data.items() if isinstance(v,str)}
        raise ValueError('Unsupported NetEase cookie format.')

    async def request(self,method,url,**kwargs):
        # These cookies go exclusively to the fixed NetEase API endpoints.
        cookie={'os':'pc','appver':'2.10.2.200154','osver':'','deviceId':'pyncm!',**self.cookies()}
        headers={'User-Agent':'Mozilla/5.0 NeteaseMusicDesktop/2.10.2.200154',
                 'Referer':'https://music.163.com/',
                 'Cookie':'; '.join(f'{k}={v}' for k,v in cookie.items())}
        response=await self.http.request(method,url,headers=headers,**kwargs)
        response.raise_for_status();data=response.json()
        if data.get('code',200)!=200:
            raise ValueError('NetEase rejected the request; check cookies and regional availability.')
        return data

    async def song_url(self,song_id):
        data=await self.request('POST','https://interface3.music.163.com/eapi/song/enhance/player/url/v1',
                                data={'params':song_url_payload(str(song_id))})
        rows=data.get('data') or []
        url=rows[0].get('url') if rows else None
        if not url:raise ValueError('NetEase did not provide audio for this song; it may be unavailable for this account.')
        return url

    @staticmethod
    def song(row):
        artists=row.get('ar') or row.get('artists') or []
        return {'kind':'song','id':row['id'],'name':row.get('name','Unknown'),
                'artists':' & '.join(x.get('name','') for x in artists),
                'album':(row.get('al') or row.get('album') or {}).get('name','')}

    async def details(self,ids):
        result=[]
        for start in range(0,len(ids),100):
            data=await self.request('POST','https://interface3.music.163.com/api/v3/song/detail',
                data={'c':json.dumps([{'id':int(x),'v':0} for x in ids[start:start+100]])})
            by_id={str(x['id']):x for x in data.get('songs',[])}
            result.extend(self.song(by_id[str(x)]) for x in ids[start:start+100] if str(x) in by_id)
        return result

    async def content(self,url):
        kind,identifier=extract_type_and_id(url)
        if not identifier.isdigit():raise ValueError('NetEase ID must be numeric.')
        if kind=='song':return {'name':'NetEase song','songs':await self.details([identifier])}
        if kind=='playlist':
            data=await self.request('POST','https://music.163.com/api/v6/playlist/detail',data={'id':identifier})
            collection=data.get('playlist',{})
            ids=[x['id'] for x in collection.get('trackIds',[])][:self.max_tracks]
            return {'name':collection.get('name','Playlist'),'songs':await self.details(ids)}
        if kind=='album':
            data=await self.request('GET',f'https://music.163.com/api/v1/album/{identifier}')
            return {'name':data.get('album',{}).get('name','Album'),
                    'songs':[self.song(x) for x in data.get('songs',[])[:self.max_tracks]]}
        if kind=='artist':
            data=await self.request('GET',f'https://music.163.com/api/v1/artist/{identifier}')
            return {'name':data.get('artist',{}).get('name','Artist'),
                    'songs':[self.song(x) for x in data.get('hotSongs',[])[:self.max_tracks]]}
        raise ValueError('Use a NetEase song, album, playlist or artist link.')

    async def search(self,query):
        results=[]
        for kind,search_type,limit in [('song',1,4),('album',10,4),('playlist',1000,2)]:
            payload={'s':query,'type':str(search_type),'limit':str(limit),'offset':'0','total':'true','csrf_token':''}
            data=await self.request('POST','https://music.163.com/weapi/search/get',data=weapi_encrypt(payload))
            rows=data.get('result',{})
            entries=rows.get({'song':'songs','album':'albums','playlist':'playlists'}[kind]) or rows.get('playLists') or []
            for row in entries[:limit]:
                if kind=='song':results.append(self.song(row))
                else:results.append({'kind':kind,'id':row['id'],'name':row.get('name',kind.title()),
                                     'artists':(row.get('artist') or {}).get('name','')})
        return results
