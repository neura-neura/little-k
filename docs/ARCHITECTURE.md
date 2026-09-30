# Architecture

A dedicated **normal Telegram account** connects through Telethon (MTProto).
This is a user account, not a BotFather bot. The owner's personal account is
separate. Incoming updates are filtered by private-user and group allowlists;
outgoing messages and the dedicated account's own messages are ignored.

Little K forwards requests to a native Hermes profile through its loopback API.
The profile controls its model, provider, personality and tools. The gateway does
not configure a second model or duplicate provider credentials. Native sessions
are mapped separately per Telegram chat and topic. Auxiliary intent and pure
translation sessions use the same profile and are removed after use.

Responses follow an internal JSON protocol; only the visible text reaches
Telegram. Presentation repair does not repeat tool execution. Connection failures
are retried; ambiguous generation timeouts are not replayed automatically.
SQLite tracks deduplication, session mappings and up to 1,000 own replies for
translation/editing. Only Little K's own messages can be edited.

Voice uses macOS `say`, ffmpeg and PyTgCalls/NTgCalls. The gateway joins an existing
group call with `auto_start=False`, waits for connection, then feeds a native PCM
file at 48 kHz stereo. A short silence margin protects brief clips. Per-group
queues preserve playback order, idle calls are left automatically, and interrupted
jobs are not replayed after a crash. It does not record or transcribe incoming audio.

A private Unix socket reports service state to local diagnostics. A file lock
prevents concurrent gateway/authorization access to the Telegram SQLite session.
The macOS LaunchAgent starts at user login and restarts the gateway after failure.
Hermes remains a separate native service.

Hermes reference documentation:

- [Native profiles](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/profiles.md)
- [Native API](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/api-server.md)
- [Profile multiplexing](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/multi-profile-gateways.md)
