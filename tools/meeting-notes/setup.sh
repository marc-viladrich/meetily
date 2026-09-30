#!/bin/sh
set -eu
TASK_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
command -v ffmpeg >/dev/null || { printf '%s\n' 'Install ffmpeg first (macOS: brew install ffmpeg).' >&2; exit 1; }
python3 -c 'import sys; assert sys.version_info >= (3, 12), "Python 3.12 or newer is required"'
python3 -m venv "$TASK_ROOT/.venv-meeting-notes"
"$TASK_ROOT/.venv-meeting-notes/bin/python" -m pip install -r "$TASK_ROOT/tools/meeting-notes/requirements.txt"
exec "$TASK_ROOT/tools/meeting-notes/meeting-notes" setup-models
