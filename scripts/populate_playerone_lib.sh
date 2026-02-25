#!/bin/bash
# Ensure Player One SDK is present on Linux: download + extract if missing; populate lib/ if needed.
# Run from repo root. Invoked by start_preview.sh, start_experiment.sh, etc. on Linux.
# When SDK dir is missing: download tarball and full-extract to repo root.
# When SDK dir exists but lib/ is missing: download and copy lib/ (real .so files) for Pi.

if [ "$(uname -s)" != "Linux" ]; then
  exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

SDK_DIR="PlayerOne_Camera_SDK_Linux_V3.10.0"
URL="https://player-one-astronomy.com/download/softwares/PlayerOne_Camera_SDK_Linux_V3.10.0.tar.gz"
TARBALL="/tmp/PlayerOne_SDK_$$.tar.gz"

cleanup_tarball() { rm -f "$TARBALL"; }
trap cleanup_tarball EXIT

# Case 1: SDK directory missing — download and full extract
if [ ! -d "$SDK_DIR" ]; then
  echo "Player One SDK: downloading and extracting (full SDK)..."
  if ! wget -q -O "$TARBALL" "$URL"; then
    echo "Player One SDK: download failed (no network?). Continuing without SDK."
    exit 0
  fi
  if ! tar -xzf "$TARBALL" -C "$REPO_ROOT"; then
    echo "Player One SDK: extract failed. Continuing without SDK."
    exit 0
  fi
  echo "Player One SDK: extracted to $SDK_DIR"
  exit 0
fi

# Case 2: SDK dir exists but lib/ for this arch missing — download and copy lib/
if [ -d "$SDK_DIR/lib/arm64" ] || [ -d "$SDK_DIR/lib/aarch64" ]; then
  exit 0
fi

echo "Player One SDK: populating lib/ with .so files..."
if ! wget -q -O "$TARBALL" "$URL"; then
  echo "Player One SDK: download failed for lib/. Continuing."
  exit 0
fi
if ! tar -xzf "$TARBALL" -C /tmp "$SDK_DIR/lib"; then
  echo "Player One SDK: extract lib/ failed. Continuing."
  exit 0
fi
cp -r "/tmp/$SDK_DIR/lib" "$SDK_DIR/"
rm -rf "/tmp/$SDK_DIR"
echo "Player One SDK: lib/ populated. You can commit and push for Windows→Pi: git add $SDK_DIR/lib/"
exit 0
