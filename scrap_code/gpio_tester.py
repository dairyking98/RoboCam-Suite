#!/usr/bin/env python3
"""
Barebones GPIO tester with GUI for debugging pins on Raspberry Pi.
Uses lgpio (Bookworm/Pi 5) or RPi.GPIO. Run on the Pi: python scrap_code/gpio_tester.py
"""

import sys
import tkinter as tk
from tkinter import ttk, messagebox

# GPIO backend: lgpio first (Pi 5 / Bookworm), then RPi.GPIO
_lgpio = None
_GPIO = None
try:
    import lgpio
    _lgpio = lgpio
except ImportError:
    pass
if _lgpio is None:
    try:
        import RPi.GPIO as GPIO
        _GPIO = GPIO
    except ImportError:
        pass

# BCM pins commonly used for general-purpose output (excluding 0, 1 = I2C; 2, 3 = I2C; 14, 15 = UART)
BCM_PINS = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27]


class GPIOTesterApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("GPIO Pin Tester")
        self.root.minsize(280, 180)
        self.root.resizable(True, True)

        self._use_lgpio = False
        self._lgpio_handle = None
        self._lgpio_chip = 0
        self._current_pin: int | None = None

        if _lgpio is None and _GPIO is None:
            self._show_no_gpio_and_quit()
            return

        self._build_ui()
        self._on_closing = None
        self.root.protocol("WM_DELETE_WINDOW", self._quit)

    def _show_no_gpio_and_quit(self):
        messagebox.showerror(
            "GPIO unavailable",
            "No GPIO library found. On Raspberry Pi install:\n  sudo apt install python3-lgpio",
        )
        self.root.destroy()
        sys.exit(1)

    def _build_ui(self):
        main = ttk.Frame(self.root, padding=12)
        main.pack(fill=tk.BOTH, expand=True)

        # Pin selection
        row0 = ttk.Frame(main)
        row0.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(row0, text="Pin (BCM):").pack(side=tk.LEFT, padx=(0, 8))
        self.pin_var = tk.StringVar(value=str(BCM_PINS[0]))
        self.pin_combo = ttk.Combobox(
            row0,
            textvariable=self.pin_var,
            values=[str(p) for p in BCM_PINS],
            state="readonly",
            width=8,
        )
        self.pin_combo.pack(side=tk.LEFT, padx=(0, 8))

        # Update button
        self.update_btn = ttk.Button(row0, text="Update", command=self._update_pin)
        self.update_btn.pack(side=tk.LEFT)

        # ON / OFF
        row1 = ttk.Frame(main)
        row1.pack(fill=tk.X, pady=8)
        self.on_btn = ttk.Button(row1, text="ON", command=self._on, width=10)
        self.on_btn.pack(side=tk.LEFT, padx=(0, 8))
        self.off_btn = ttk.Button(row1, text="OFF", command=self._off, width=10)
        self.off_btn.pack(side=tk.LEFT)

        # Status
        self.status_var = tk.StringVar(value="Select pin and click Update.")
        status_lbl = ttk.Label(main, textvariable=self.status_var)
        status_lbl.pack(anchor=tk.W, pady=(8, 0))

        self._set_output_buttons_state(tk.DISABLED)

    def _set_output_buttons_state(self, state):
        self.on_btn.config(state=state)
        self.off_btn.config(state=state)

    def _release_current_pin(self):
        """Release current pin (set LOW and cleanup)."""
        if self._current_pin is None:
            return
        pin = self._current_pin
        self._current_pin = None
        self._set_output_buttons_state(tk.DISABLED)
        try:
            if self._use_lgpio and self._lgpio_handle is not None and self._lgpio_handle >= 0:
                _lgpio.gpio_write(self._lgpio_handle, pin, 0)
                _lgpio.gpiochip_close(self._lgpio_handle)
                self._lgpio_handle = None
            elif _GPIO is not None:
                _GPIO.output(pin, _GPIO.LOW)
                _GPIO.cleanup(pin)
        except Exception:
            pass

    def _update_pin(self):
        """Apply selected pin: release previous, setup new as OUTPUT, set LOW."""
        try:
            pin = int(self.pin_var.get().strip())
        except ValueError:
            self.status_var.set("Invalid pin number.")
            return
        if pin not in BCM_PINS:
            self.status_var.set(f"Pin {pin} not in allowed list.")
            return

        self._release_current_pin()

        if _lgpio is not None:
            try:
                h = _lgpio.gpiochip_open(self._lgpio_chip)
                if h >= 0:
                    _lgpio.gpio_claim_output(h, pin, 0)
                    self._lgpio_handle = h
                    self._use_lgpio = True
                    self._current_pin = pin
                    self.status_var.set(f"GPIO {pin} ready (lgpio). Use ON/OFF.")
                    self._set_output_buttons_state(tk.NORMAL)
                    return
            except Exception as e:
                self.status_var.set(f"lgpio error: {e}")
                if self._lgpio_handle is not None and self._lgpio_handle >= 0:
                    try:
                        _lgpio.gpiochip_close(self._lgpio_handle)
                    except Exception:
                        pass
                    self._lgpio_handle = None
                self._use_lgpio = False

        if _GPIO is not None:
            try:
                _GPIO.setmode(_GPIO.BCM)
                _GPIO.setwarnings(False)
                _GPIO.setup(pin, _GPIO.OUT)
                _GPIO.output(pin, _GPIO.LOW)
                self._current_pin = pin
                self._use_lgpio = False
                self.status_var.set(f"GPIO {pin} ready (RPi.GPIO). Use ON/OFF.")
                self._set_output_buttons_state(tk.NORMAL)
            except Exception as e:
                self.status_var.set(f"RPi.GPIO error: {e}")

    def _on(self):
        if self._current_pin is None:
            return
        try:
            if self._use_lgpio and self._lgpio_handle is not None:
                _lgpio.gpio_write(self._lgpio_handle, self._current_pin, 1)
            else:
                _GPIO.output(self._current_pin, _GPIO.HIGH)
            self.status_var.set(f"GPIO {self._current_pin} ON")
        except Exception as e:
            self.status_var.set(f"Error: {e}")

    def _off(self):
        if self._current_pin is None:
            return
        try:
            if self._use_lgpio and self._lgpio_handle is not None:
                _lgpio.gpio_write(self._lgpio_handle, self._current_pin, 0)
            else:
                _GPIO.output(self._current_pin, _GPIO.LOW)
            self.status_var.set(f"GPIO {self._current_pin} OFF")
        except Exception as e:
            self.status_var.set(f"Error: {e}")

    def _quit(self):
        self._release_current_pin()
        if _GPIO is not None:
            try:
                _GPIO.cleanup()
            except Exception:
                pass
        self.root.destroy()
        sys.exit(0)

    def run(self):
        self.root.mainloop()


def main():
    app = GPIOTesterApp()
    if _lgpio is None and _GPIO is None:
        return
    app.run()


if __name__ == "__main__":
    main()
