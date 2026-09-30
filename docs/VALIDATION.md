# Validation

The automated suite uses fictitious credentials and mocked Telegram/Hermes/call
interfaces. It runs without `.env`, a Telegram session or a local Hermes service.
It covers configuration portability, identity/access filtering, parser behavior,
English help, session isolation, persistence, deduplication, translation editing,
concurrency, safe HTTP retries, voice queues and cleanup.

```sh
.venv/bin/python -m pytest -q
.venv/bin/python -m pip check
```

GitHub Actions runs the suite on macOS with Python 3.12. Automated tests do not
prove a real account can speak in a particular Telegram group.

For your installation:

```sh
.venv/bin/python -m scripts.doctor --skip-service
# After installing the LaunchAgent:
.venv/bin/python -m scripts.doctor
```

Doctor checks the environment, imports, Telegram identity/session, authenticated
Hermes profile API, SQLite integrity, ffmpeg and real local TTS in four languages.
While the gateway owns the Telegram session, doctor reads its private diagnostic
socket instead of opening the session a second time. Reports remain private in
`data/doctor.json`.

Manual acceptance: message the dedicated account from the owner account; check
`.h`; send `.t zh What is 5 + 5?` in an allowed group; open a group voice chat and
send `.c Introduce yourself in one sentence.` Confirm a separate participant,
audible speech and idle departure. Test `.t zh .c Tell me a fun fact.` too.
The original installation passed these real Telegram text and audible voice tests.
Auto-start after a physical reboot needs verification on each user's machine.
