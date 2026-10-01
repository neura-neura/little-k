# Voice presets and media playback

`.voice` shows the selected speech backend. The owner can switch it with:

```text
.voice macos
.voice gtts
.voice gtts mx
```

`macos` preserves the existing local voices. `gtts` reproduces the earlier
userbot's Google Translate TTS method: Spanish `es`, English `en`, Mandarin
`zh-CN`, default domain `com`. Optional domain/accent presets are `default`
(`com`), `mx` (`com.mx`), `es` (`es`), `uk` (`co.uk`), `au` (`com.au`), `ie`
(`ie`) and `in` (`co.in`). The default preset matches that project's saved user
settings. Accent support varies by language.

The choice is **global**, persisted in the private SQLite `settings` table and
applied to speech queued after the change. It survives `.env` reloads, service
restarts and machine reboots. Queued speech keeps the preset it was queued with.
No provider failure silently switches your selected backend. gTTS needs internet
and sends the speech text to Google's TTS service; macOS speech is local.

## Media commands

```text
.play https://www.youtube.com/watch?v=VIDEO_ID
.play https://www.bilibili.com/video/VIDEO_ID
.play https://music.163.com/song?id=SONG_ID
.play https://open.spotify.com/track/TRACK_ID
.pick 1
.pause
.resume
.next
.previous
.queue
.stop
```

A **bare supported URL** also requests playback. Reply to a supported link with
`.play` to use the replied-to URL. Mentioning a link within ordinary conversation
does not automatically request music. Media controls are available to users in
allowed groups; account/allowlist checks and incoming-message deduplication still
apply. The global voice switch is owner-only.

YouTube (including YouTube Music) and Bilibili use yt-dlp to download the selected
video's audio. Playlist-only YouTube URLs play the first item. NetEase supports
song, album, playlist and artist URLs; collections advance automatically.
`.next`/`.previous` navigate the current NetEase collection. `.next` skips a
standalone item while keeping other queued items.

Spotify is a **metadata-to-NetEase lookup**, like the previous userbot. It does
not download Spotify's audio: choose a NetEase song/album/playlist with
`.pick <number>` within five minutes. Selections belong to the requesting user.
`.pick 0` cancels. Results can be covers or different releases: inspect the list.
Unavailable tracks or account/region restrictions remain unavailable.

All speech and music share a per-group queue and the proven native PCM playback
path. Little K only joins an existing voice chat, never creates one. It leaves
after inactivity. Pause keeps the active stream open. Stop cancels the active
preparation/playback, clears the queue/collection and leaves the call. Collection
navigation replaces current queued audio. Playback state and pending selections
are not replayed after a restart; only the speech preset is persistent.

## Dependencies and cookies

Run `./install.sh` after updating to install gTTS, yt-dlp, its EJS challenge
package and the NetEase encryption dependencies. YouTube also needs a supported
JavaScript runtime. Install `deno` or a current Node.js, available on the service's
PATH. yt-dlp/EJS versions may need updates as media platforms change.

Set these private paths in `.env` if authentication is needed:

```dotenv
YOUTUBE_COOKIES_PATH=secrets/cookies/youtube.txt
BILIBILI_COOKIES_PATH=secrets/cookies/bilibili.txt
NETEASE_COOKIES_PATH=secrets/cookies/netease.json
```

YouTube/Bilibili cookies use Netscape cookie-file format. Raw browser `Cookie`
headers can be imported without exposing their values:

```sh
.venv/bin/python -m scripts.import_cookies --bilibili /path/to/bilibili.txt --netease /path/to/music.163.com.txt
```

The importer accepts header text, Netscape exports or JSON, writes the private
configured-default files and converts NetEase cookies to JSON. NetEase accepts the
previous project's JSON cookie list or a name/value object. These files grant
account access: `secrets/` and `*cookies*.txt`/`*cookies*.json` are ignored by Git.
Keep directories mode `0700` and cookie files mode `0600`. yt-dlp receives a
temporary private cookie copy so downloads do not overwrite your source cookie
jar. Cookies are sent to the platform API; NetEase audio CDN requests receive no
account cookies. Generated audio and temporary copies are removed after use.

Defaults: download/preparation timeout 300 seconds, duration 7,200 seconds (two hours),
source-file cap 200 MiB, collections up to 100 tracks. Change `MEDIA_TIMEOUT`,
`MEDIA_MAX_DURATION`, `MEDIA_MAX_BYTES` or `MEDIA_MAX_TRACKS` in `.env` and use
`/k reload`. Conversion preserves 48 kHz stereo PCM plus the existing short
silence margin. Music never passes through Hermes or TTS.

References: [gTTS accents](https://gtts.readthedocs.io/en/stable/module.html),
[yt-dlp](https://github.com/yt-dlp/yt-dlp),
[YouTube JavaScript support](https://github.com/yt-dlp/yt-dlp/wiki/EJS).
