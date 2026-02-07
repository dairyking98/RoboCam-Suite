"""One-off: replace 5.4.1 block in PLAYER_ONE_MARS_SDK.md."""
path = "docs/PLAYER_ONE_MARS_SDK.md"
with open(path, "r", encoding="utf-8") as f:
    lines = f.read().split("\n")

# Find "#### 5.4.1 Pushed from Windows" and "#### 5.5"
start = end = -1
for i, line in enumerate(lines):
    if "#### 5.4.1" in line and "Pushed from Windows" in line:
        start = i
    if start >= 0 and "#### 5.5" in line:
        end = i
        break

new_541 = """#### 5.4.1 Pushed from Windows – will it work on the Pi?

**Yes, once the repo has real `.so` files in `PlayerOne_Camera_SDK_Linux_V3.10.0/lib/`.** The repo tracks that folder (no symlinks). Push from Windows works on the Pi after that.

**If `lib/` is not in the repo yet:** run `scripts/populate_playerone_lib.sh` on the Pi once. It downloads the SDK tarball, extracts it, and copies `lib/` into the project SDK folder. Then run `git add PlayerOne_Camera_SDK_Linux_V3.10.0/lib/`, commit, and push. After that, push-from-Windows works on the Pi."""

if start >= 0 and end >= 0:
    new_lines = lines[:start] + new_541.strip().split("\n") + [""] + lines[end:]
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(new_lines))
    print("Replaced 5.4.1 block.")
else:
    print("5.4.1 block not found.", start, end)
