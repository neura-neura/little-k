#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
umask 077
if [ "$(uname -s)" != Darwin ] || [ "$(uname -m)" != arm64 ]; then
  echo 'Supported installation: macOS 14+ on Apple Silicon.' >&2
  exit 1
fi
if [ "$(sw_vers -productVersion | cut -d. -f1)" -lt 14 ]; then
  echo 'macOS 14 or newer is required by the voice library.' >&2
  exit 1
fi
PYTHON_BIN=${PYTHON_BIN:-python3.12}
"$PYTHON_BIN" -c 'import sys; assert sys.version_info[:2] == (3,12), "Python 3.12 required"'
if [ ! -x .venv/bin/python ]; then "$PYTHON_BIN" -m venv .venv; fi
.venv/bin/python -c 'import sys; assert sys.version_info[:2] == (3,12), "Existing .venv must use Python 3.12"'
.venv/bin/python -m pip install -r requirements.txt
if [ ! -f .env ]; then cp .env.example .env; fi
chmod 600 .env
mkdir -p data logs
chmod 700 data logs
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo 'Install ffmpeg (brew install ffmpeg), or set FFMPEG_PATH in .env.'
fi
printf '%s\n' 'Dependencies ready. Fill in .env, then follow the README setup steps.'
