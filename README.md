# Little K

A Telegram interface for a **native Hermes AI profile**, with multilingual text,
translation and free local speech in Telegram group voice chats. Little K uses
its own dedicated normal Telegram account through MTProto. Your personal account
remains separate. Hermes supplies the model, provider, personality and tools.

## Requirements

The supported, tested installation is **macOS 14 or newer on Apple Silicon**,
with **Python 3.12**, ffmpeg and a working [Hermes installation](https://github.com/NousResearch/hermes-agent).
The current voice backend uses macOS `say`; this distribution does not promise
Linux, Windows or Intel Mac support. The machine must stay awake and online.

You also need:

- A Telegram application API ID and API hash from [my.telegram.org/apps](https://my.telegram.org/apps).
- A dedicated normal Telegram account for Little K, including access to its login
  code and 2FA password. A BotFather token cannot replace these credentials.
- Your personal Telegram user ID and the IDs of any groups/users you allow.
- Hermes configured with your model/provider credentials. Provider/tool access
  and any associated usage charges belong to that Hermes configuration.

Install Python 3.12 from [python.org](https://www.python.org/downloads/) or your
package manager. With Homebrew, the prerequisites are:

```sh
brew install python@3.12 ffmpeg
```

## Quick start

```sh
git clone https://github.com/neura-neura/little-k.git
cd little-k
./install.sh
```

The installer creates `.venv`, installs pinned dependencies and copies
`.env.example` to `.env` **only if `.env` does not already exist**. Set
`PYTHON_BIN=/path/to/python3.12` when Python is not on PATH.

Edit `.env` with your own values:

```dotenv
TELEGRAM_API_ID=YOUR_API_ID
TELEGRAM_API_HASH=YOUR_API_HASH
OWNER_USER_ID=YOUR_PERSONAL_USER_ID
LITTLE_K_TELEGRAM_USER_ID=
ALLOWED_CHAT_IDS=YOUR_GROUP_ID
ALLOWED_PRIVATE_USER_IDS=
```

Use numeric IDs, not usernames, phone numbers or BotFather tokens. Allowlist
entries are comma-separated. Leave lists empty to allow only the owner in private
chat. Groups typically have negative IDs beginning with `-100`; preserve the
full ID. Obtain these IDs from a trusted Telegram ID lookup tool. Leave
`LITTLE_K_TELEGRAM_USER_ID` empty initially: authorization fills it automatically.

### Connect Hermes

First install Hermes and complete its native model/provider setup. Little K does
not install Hermes or choose a model for you. With Hermes configured:

```sh
.venv/bin/python -m scripts.setup_hermes
hermes --profile default gateway restart
```

The helper creates the `little-k` native profile by cloning the default profile's
configuration, gives a **new profile** the included kitten personality, provisions
separate API keys and enables native profile multiplexing. Existing Little K
personality/model settings are preserved. Native cloning can copy curated memory
and skills; review the profile in Hermes if you want a clean personality/context.
A private backup of the root Hermes environment is kept in `data/` before changes.
Restarting Hermes applies the API settings to the shared native listener.

If you have not installed a native Hermes gateway service, run
`hermes --profile default gateway run` in another terminal instead of restarting.
The Hermes gateway must remain running alongside Little K. See the native
[Hermes CLI reference](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/reference/cli-commands.md)
for service installation on your system.

The default API URL is `http://127.0.0.1:8642/p/little-k`. Configure
`HERMES_PROFILE`, `HERMES_BASE_URL` and `HERMES_KEY_FILE` consistently if you use
another profile, port or Hermes home. The helper honors `HERMES_HOME` and
`HERMES_CLI` environment variables. It refuses to change an existing API port
that disagrees with your URL. The gateway accepts only loopback Hermes URLs.

For an already configured native profile/API, skip the helper and point
`HERMES_KEY_FILE` to its `.env` containing `API_SERVER_KEY`, or set
`HERMES_API_KEY` directly. Model/provider credentials stay inside Hermes.

### Authorize and run

```sh
.venv/bin/python -m scripts.authorize_telegram
.venv/bin/python -m scripts.doctor --skip-service
./run.sh
```

Enter the **dedicated Little K account's** phone number, Telegram code and 2FA
password when requested. The script rejects your owner account and bot accounts,
saves the authorized session locally and records the dedicated account ID in
`.env`. Subsequent launches reuse the session without asking for a code.

Add the dedicated account to your allowed groups and grant permission to speak
in their voice chats. From your personal account, open a private chat with Little K
and send a message. Send `.h` for the full English command reference.

Stop the foreground process with Ctrl+C before installing the background service:

```sh
.venv/bin/python -m scripts.service install
.venv/bin/python -m scripts.doctor
```

The LaunchAgent starts at macOS user login and restarts Little K if it fails.
Installation resolves paths from your clone; no developer-specific paths are
required. If you move the clone, reinstall the service from the new location.
Hermes has its own service lifecycle.

## Commands

| Command | Behavior |
| --- | --- |
| `.h` | Show English help; the owner also sees administrative commands. |
| `.t en` | Translate text or a replied-to message into English. |
| `.t zh What is 5 + 5?` | Answer the question in Chinese. |
| `.t` | Default translation: Spanish → Chinese; Chinese → Spanish; other → Spanish. |
| `.c Introduce yourself.` | Send text and read it in this group's active voice chat. |
| `.t zh .c Tell me a fun fact.` | Answer in Chinese and speak it in the call. |
| Reply + `.c` | Read the quoted text aloud; combine with `.t` to translate first. |

Shortcuts are case-insensitive, can appear in either order, and support `.tzh`
and `.t.zh`. Translation language codes include `es`, `en`, `zh`, `ja`, `ko`,
`fr`, `de`, `pt` and `it`; `.h` lists all supported text codes. Spoken output
requires a configured, installed system voice for that language.

In allowed private chats, write normally. In allowed groups, mention Little K,
reply to it, start with “Little K,” or use a shortcut. Natural language such as
“Little K, answer in Chinese and read it in the call” also works through Hermes.
Members of an allowed group can address Little K; only the owner can administer it.

Owner-only controls:

| Command | Behavior |
| --- | --- |
| `/k status` | Check Telegram, Hermes and voice state. |
| `/k new` | Start a fresh conversation for this chat/topic. |
| `/k voice status` | Show connection, playback and queue state. |
| `/k voice stop` | Stop playback, clear the queue and leave the call. |
| `/k voice clear` | Clear waiting audio while current playback continues. |
| `/k reload` | Reload access lists/settings; account changes require a restart. |

Translations of Little K's recorded replies are added to its own original message
when editing is possible, otherwise sent separately. Flag reactions can request
English/Chinese translations where Telegram exposes the reactor's identity;
reply + `.t` is the reliable alternative. Normal Telegram accounts do not support
Bot API callback buttons.

## Voice settings

Default voices: Paulina (Spanish), Samantha (English), Tingting (Chinese), Kyoko
(Japanese), Yuna (Korean). Inspect available voices with:

```sh
say -v '?'
```

Install missing voices through macOS System Settings → Accessibility → Spoken
Content (or Read & Speak, depending on macOS version), then set `VOICE_ES`,
`VOICE_EN`, etc. in `.env`. `FFMPEG_PATH` can be empty to use PATH or contain an
absolute executable path. `VOICE_IDLE_TIMEOUT` defaults to 20 seconds.

Little K joins **existing** group calls and never creates one automatically.
It uses its dedicated account as a separate participant. If admins mute it, they
must allow it to speak. Text is still delivered when audio cannot play. There is
no recording or speech recognition of incoming audio.

## Configuration and maintenance

See [.env.example](.env.example) for every setting. Paths may be relative to the
clone or use `~`. Environment variables override dotenv values. Existing
installations can keep the legacy credential/access-list `.env` files; the main
`.env` takes precedence. New installations use only `.env`.

```sh
.venv/bin/python -m scripts.service status
.venv/bin/python -m scripts.service restart
.venv/bin/python -m scripts.service stop
.venv/bin/python -m scripts.service start
.venv/bin/python -m scripts.service uninstall
.venv/bin/python -m pytest -q
.venv/bin/python -m pip check
```

Uninstall removes only Little K's LaunchAgent. It preserves your source, session,
data and Hermes profile. Stop Little K before reauthorizing Telegram or updating
its environment. After pulling an update, rerun `./install.sh`, tests and doctor,
then restart the service. Change the profile's model/personality/tools in Hermes;
use `/k new` when an existing conversation still has earlier session settings.

Private files are ignored by Git: `.env`, Telegram `.session` files, `data/`,
`logs/` and generated audio. A Telegram session grants access to the dedicated
account: never publish or share it. Keep environment/session files mode `0600`.
The SQLite state contains conversation mappings and recent own replies, and
Hermes maintains its native history separately. Logs rotate and omit full
message bodies and secrets. Review allowlists and the tools enabled in your
Hermes profile before granting other people access.

## Troubleshooting

Run doctor first. If it reports Telegram errors, check credentials, the authorized
account, allowlists and service state. If Hermes fails, verify its gateway is
running, the profile route is enabled and the **profile's own API key** is used.
If voice fails, check an active call in that same group, permission to speak,
installed voices and ffmpeg. Inspect `logs/little-k.log` locally.

The gateway recovers when Hermes restarts. Requests with ambiguous delivery after
a crash or timeout are not automatically replayed; resend the request if needed.
Interrupted voice jobs are not replayed on restart either.

See [architecture](docs/ARCHITECTURE.md) and [validation](docs/VALIDATION.md) for
implementation details, test coverage and manual acceptance checks.
