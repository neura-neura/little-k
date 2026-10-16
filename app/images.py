"""Bounded Telegram image inputs for the native Hermes vision API."""
import base64

MAX_IMAGE_BYTES=5*1024*1024


def is_image(message):
    if message is None:return False
    if getattr(message,'photo',None):return True
    document=getattr(message,'document',None)
    return bool(document and getattr(document,'mime_type','') in ('image/jpeg','image/png','image/webp','image/gif'))


async def image_part(client,message):
    if not is_image(message):return None
    file=getattr(message,'file',None)
    if (getattr(file,'size',0) or 0)>MAX_IMAGE_BYTES:
        raise ValueError('La imagen supera 5 MB; envíala como foto comprimida o reduce su tamaño.')
    data=await client.download_media(message,file=bytes)
    if not data:raise ValueError('No pude descargar la imagen de Telegram.')
    if len(data)>MAX_IMAGE_BYTES:raise ValueError('La imagen supera 5 MB; reduce su tamaño.')
    if data.startswith(b'\xff\xd8\xff'):mime='image/jpeg'
    elif data.startswith(b'\x89PNG\r\n\x1a\n'):mime='image/png'
    elif data[:6] in (b'GIF87a',b'GIF89a'):mime='image/gif'
    elif data.startswith(b'RIFF') and data[8:12]==b'WEBP':mime='image/webp'
    else:raise ValueError('Formato de imagen no compatible. Usa JPEG, PNG, WebP o GIF.')
    return {'type':'image_url','image_url':{'url':'data:'+mime+';base64,'+base64.b64encode(data).decode()}}
