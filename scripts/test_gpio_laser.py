#!/usr/bin/env python3
"""
Test that the configured GPIO pin actually outputs 3.3V when set HIGH.

Usage (on Raspberry Pi):
  python3 scripts/test_gpio_laser.py

The script uses the same config as the app (hardware.laser.gpio_pin), sets that
pin HIGH for 10 seconds, then LOW. Use a multimeter or your laser to verify.

BCM vs physical pin: The config uses BCM (Broadcom) numbers, not physical pin
positions. Example: BCM 21 = physical pin 40. If your wire is on physical pin 21,
that is BCM 9 — set gpio_pin to 9 in config/default_config.json.
"""

import sys
import time

# BCM number -> physical pin (40-pin header, Pi 4 style)
BCM_TO_PHYSICAL = {
    2: 3, 3: 5, 4: 7, 17: 11, 27: 13, 22: 15, 23: 16, 24: 18, 25: 22,
    5: 29, 6: 31, 12: 32, 13: 33, 19: 35, 26: 37, 16: 36, 20: 38, 21: 40,
    7: 26, 8: 24, 9: 21, 10: 19, 11: 23, 14: 8, 15: 10, 18: 12,
}


def main():
    try:
        import RPi.GPIO as GPIO
    except ImportError:
        print("RPi.GPIO not found. Run this script on a Raspberry Pi.")
        sys.exit(1)

    try:
        from robocam.config import get_config
        config = get_config()
        bcm_pin = config.get("hardware.laser.gpio_pin", 21)
    except Exception as e:
        print(f"Could not load config: {e}")
        bcm_pin = 21

    physical = BCM_TO_PHYSICAL.get(bcm_pin, "?")
    print(f"Config pin: BCM {bcm_pin} (physical pin {physical} on 40-pin header)")
    print(f"If your wire is on a different physical pin, change hardware.laser.gpio_pin in config.")
    print()

    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    # Release pin in case a previous run (or another script) left it claimed
    try:
        GPIO.cleanup(bcm_pin)
    except Exception:
        GPIO.cleanup()
    time.sleep(0.1)

    try:
        GPIO.setup(bcm_pin, GPIO.OUT)
    except RuntimeError as e:
        if "in use" in str(e).lower() or "already" in str(e).lower():
            print(f"Pin BCM {bcm_pin} is in use (often by the system on this Pi/OS).")
            print("Try a different pin in config, e.g. gpio_pin: 17 (physical 11) or gpio_pin: 27 (physical 13).")
        raise

    GPIO.output(bcm_pin, GPIO.LOW)
    time.sleep(0.2)

    print("Setting pin HIGH for 10 seconds (measure 3.3V or connect laser)...")
    GPIO.output(bcm_pin, GPIO.HIGH)
    time.sleep(10)
    print("Setting pin LOW.")
    GPIO.output(bcm_pin, GPIO.LOW)
    GPIO.cleanup()
    print("Done.")


if __name__ == "__main__":
    main()
