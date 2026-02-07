#!/bin/bash
# One-time: populate PlayerOne_Camera_SDK_Linux_V3.10.0/lib/ with real .so files
# so the repo can be pushed from Windows and work on Raspberry Pi (no symlinks).
# Run from repo root. Run on the Pi (or any Linux) if lib/ is missing after clone.

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"
SDK_DIR="PlayerOne_Camera_SDK_Linux_V3.10.0"
URL="https://player-one-astronomy.com/download/softwares/PlayerOne_Camera_SDK_Linux_V3.10.0.tar.gz"

if [ ! -d "$SDK_DIR" ]; then
  echo "Error: $SDK_DIR not found. Run from repo root."
  exit 1
fi

if [ -d "$SDK_DIR/lib/arm64" ] || [ -d "$SDK_DIR/lib/aarch64" ]; then
  echo "lib/ already present. Nothing to do."
  exit 0
fi

echo "Downloading SDK tarball to populate lib/ with real .so files..."
wget -q -O /tmp/PlayerOne_SDK.tar.gz "$URL" || { echo "Download failed."; exit 1; }
echo "Extracting lib/..."
tar -xzf /tmp/PlayerOne_SDK.tar.gz -C /tmp PlayerOne_Camera_SDK_Linux_V3.10.0/lib
cp -r /tmp/PlayerOne_Camera_SDK_Linux_V3.10.0/lib "$SDK_DIR/"
rm -f /tmp/PlayerOne_SDK.tar.gz
rm -rf /tmp/PlayerOne_Camera_SDK_Linux_V3.10.0
echo "Done. Add and commit the lib/ folder so push-from-Windows works on Pi:"
echo "  git add $SDK_DIR/lib/"
echo "  git commit -m 'Add Player One SDK lib (real .so files)'"
echo "  git push"
