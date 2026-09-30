#!/bin/sh
# Fetch by default; opt into a regular merge on the integration branch.
set -eu
TASK_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$TASK_ROOT"
git fetch upstream main --tags
case "${1:-}" in
  '')
    git log --oneline HEAD..upstream/main
    printf '%s\n' 'To integrate these commits: scripts/sync-marc-upstream.sh --merge'
    ;;
  --merge)
    [ "$(git branch --show-current)" = 'marc/meeting-transcripts' ] || {
      printf '%s\n' 'Switch to marc/meeting-transcripts first.' >&2; exit 1;
    }
    [ -z "$(git status --porcelain)" ] || {
      printf '%s\n' 'Commit or stash your changes first.' >&2; exit 1;
    }
    git merge --no-edit upstream/main
    PYTHONPATH=tools/meeting-notes python3 -m unittest discover -s tools/meeting-notes/tests -v
    printf '%s\n' 'Run the model smoke test before pushing. No push was performed.'
    ;;
  *) printf '%s\n' 'Usage: scripts/sync-marc-upstream.sh [--merge]' >&2; exit 1 ;;
esac
