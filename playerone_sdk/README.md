# Player One SDK (project-local)

Optional: put a **minimal** copy of the Player One SDK here if you don't want to place the full SDK folder in the project root.

**Simpler option:** Put the **entire** extracted SDK (e.g. `PlayerOne_Camera_SDK_Linux_V3.10.0`) directly in the RoboCam-Suite root. The app will use it automatically. See **docs/PLAYER_ONE_MARS_SDK.md** section 5.4.

---

## Layout (this folder)

```
playerone_sdk/
├── README.md          (this file)
├── native/            ← put the .so library here
│   └── libPlayerOne_camera.so   (or libPlayerOneCamera.so)
└── python/            ← put the SDK Python bindings here
    ├── pyPOACamera.py           (patched for Linux)
    └── ... (other .py files from the SDK python folder)
```

## Setup

1. **Download the SDK**  
   From [Player One software page](https://player-one-astronomy.com/service/software/), get the Linux SDK (e.g. `PlayerOne_Camera_SDK_Linux_V3.10.0.tar.gz`). Extract it somewhere (e.g. `~/PlayerOne_Camera_SDK_Linux_V3.10.0`).

2. **Copy the library into `native/`**  
   From the extracted SDK, copy the shared library for your system (e.g. from `lib/arm64/` on 64-bit Raspberry Pi):

   ```bash
   mkdir -p playerone_sdk/native
   cp ~/PlayerOne_Camera_SDK_Linux_V3.10.0/lib/arm64/libPlayerOne_camera.so playerone_sdk/native/
   ```

   If the SDK expects a different name (e.g. `libPlayerOneCamera.so`), also add a symlink or copy with that name:

   ```bash
   cd playerone_sdk/native
   ln -s libPlayerOne_camera.so libPlayerOneCamera.so
   ```

3. **Copy and patch the Python bindings into `python/`**  
   Copy the SDK’s `python/` folder contents into `playerone_sdk/python/`:

   ```bash
   mkdir -p playerone_sdk/python
   cp ~/PlayerOne_Camera_SDK_Linux_V3.10.0/python/*.py playerone_sdk/python/
   ```

   Edit `playerone_sdk/python/pyPOACamera.py` so that on Linux it loads the library **by name only** (no `./`), so the loader finds it in `playerone_sdk/native/` via `LD_LIBRARY_PATH`:

   ```python
   import sys
   if sys.platform == "win32":
       dll = cdll.LoadLibrary("./PlayerOneCamera.dll")
   else:
       dll = cdll.LoadLibrary("libPlayerOne_camera.so")  # or libPlayerOneCamera.so
   ```

4. **Run the app**  
   From the RoboCam-Suite root, run `./start_preview.sh` or `./start_experiment.sh`. The launcher scripts add `playerone_sdk/native` to `LD_LIBRARY_PATH` so the library is found.

## udev (USB permissions)

You still need a udev rule so the camera is accessible without root. See **docs/PLAYER_ONE_MARS_SDK.md** (step 3).

## More details

See **docs/PLAYER_ONE_MARS_SDK.md** for full SDK install, Python patch, and OpenCV notes.
