#!/usr/bin/env python3
"""
Test that the configured GPIO pin actually outputs 3.3V when set HIGH.

Uses the same Laser class as the app (lgpio on Bookworm/Pi 5, else RPi.GPIO).
On Bookworm/Pi 5, RPi.GPIO often does not drive pins — install: sudo apt install python3-lgpio

Usage (on Raspberry Pi):
  python3 scripts/test_gpio_laser.py

BCM vs physical: config uses BCM. BCM 21 = physical pin 40. Physical 21 = BCM 9.
"""

import os
import sys
import time

# Add project root so "robocam" can be imported when run as scripts/test_gpio_laser.py
_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_script_dir)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# BCM number -> physical pin (40-pin header, Pi 4 style)
BCM_TO_PHYSICAL = {
    2: 3, 3: 5, 4: 7, 17: 11, 27: 13, 22: 15, 23: 16, 24: 18, 25: 22,
    5: 29, 6: 31, 12: 32, 13: 33, 19: 35, 26: 37, 16: 36, 20: 38, 21: 40,
    7: 26, 8: 24, 9: 21, 10: 19, 11: 23, 14: 8, 15: 10, 18: 12,
}


def main():
    try:
        from robocam.laser import Laser
    except ImportError as e:
        print(f"Could not import Laser: {e}")
        print("On Bookworm/Pi 5 install: sudo apt install python3-lgpio")
        sys.exit(1)
    except RuntimeError as e:
        print(f"GPIO not available: {e}")
        sys.exit(1)

    try:
        from robocam.config import get_config
        config = get_config()
        bcm_pin = config.get("hardware.laser.gpio_pin", 21)
    except Exception:
        bcm_pin = 21

    physical = BCM_TO_PHYSICAL.get(bcm_pin, "?")
    print(f"Config pin: BCM {bcm_pin} (physical pin {physical} on 40-pin header)")
    print("Using same Laser class as app (lgpio if installed, else RPi.GPIO).")
    print()

    try:
        laser = Laser()
    except Exception as e:
        print(f"Laser init failed: {e}")
        sys.exit(1)

    print("Setting pin HIGH for 10 seconds (measure 3.3V or connect laser)...")
    laser.switch(1)
    time.sleep(10)
    print("Setting pin LOW.")
    laser.switch(0)
    print("Done.")


if __name__ == "__main__":
    main()
