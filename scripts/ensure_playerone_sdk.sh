#!/bin/bash
# Auto-extract PlayerOne Camera SDK tarball on Linux/Raspberry Pi when any .sh is run.
# Sourced by start_preview.sh, start_experiment.sh, start_calibrate.sh, setup.sh,
# fix_dependencies.sh, and scripts/populate_playerone_lib.sh.
# Only runs on Linux; does nothing on other OS. If the archive exists in repo root
# and the SDK directory is missing, extracts it so symlinks work (no Windows privilege issue).

if [ "$(uname -s)" != "Linux" ]; then
  return 0 2>/dev/null || true
  exit 0
fi

_ensure_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${REPO_ROOT:-$(cd "$_ensure_script_dir/.." && pwd)}"
SDK_ARCHIVE="$REPO_ROOT/PlayerOne_Camera_SDK_Linux_V3.10.0.tar.gz"
SDK_DIR="$REPO_ROOT/PlayerOne_Camera_SDK_Linux_V3.10.0"

if [ -f "$SDK_ARCHIVE" ] && [ ! -d "$SDK_DIR" ]; then
  echo "Player One SDK: extracting $SDK_ARCHIVE..."
  tar -xzf "$SDK_ARCHIVE" -C "$REPO_ROOT"
  echo "Player One SDK: extracted to $SDK_DIR"
fi

unset _ensure_script_dir SDK_ARCHIVE SDK_DIR
