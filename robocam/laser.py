"""
Laser Control Module

Controls GPIO-connected laser module for experiment stimulation.
Requires Raspberry Pi GPIO hardware.

On Raspberry Pi OS Bookworm and Pi 5, RPi.GPIO often does not drive pins;
this module uses lgpio when available (kernel GPIO driver), then falls back
to RPi.GPIO. Install: sudo apt install python3-lgpio

Author: RoboCam-Suite
"""

from typing import Optional, Any
from .config import get_config, Config
from .logging_config import get_logger

logger = get_logger(__name__)

# Try lgpio first (works on Bookworm / Pi 5); fall back to RPi.GPIO
_lgpio: Any = None
_GPIO: Any = None

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


class Laser:
    """
    GPIO-controlled laser module for experiment stimulation.

    Controls a laser connected to a GPIO pin. Default pin is BCM 21.
    Uses lgpio on Bookworm/Pi 5 (so the pin actually outputs 3.3V), else RPi.GPIO.

    Attributes:
        laser_pin (int): GPIO pin number (BCM)
        ON: 1 (lgpio) or GPIO.HIGH (RPi.GPIO)
        OFF: 0 (lgpio) or GPIO.LOW (RPi.GPIO)
    """

    def __init__(self, laser_pin: Optional[int] = None, config: Optional[Config] = None) -> None:
        """
        Initialize laser control on specified GPIO pin (BCM numbering).

        Raises:
            RuntimeError: If neither lgpio nor RPi.GPIO is available or init fails
            ValueError: If GPIO pin is invalid
        """
        self.config: Config = config if config else get_config()
        laser_config = self.config.get_laser_config()
        self.laser_pin: int = laser_pin if laser_pin is not None else laser_config.get("gpio_pin", 21)

        if not (0 <= self.laser_pin <= 27):
            raise ValueError(f"Invalid GPIO pin: {self.laser_pin} (must be 0-27)")

        self._use_lgpio: bool = False
        self._lgpio_handle: Optional[int] = None
        self._lgpio_chip: int = 0

        if _lgpio is not None:
            try:
                self._lgpio_handle = _lgpio.gpiochip_open(self._lgpio_chip)
                if self._lgpio_handle >= 0:
                    _lgpio.gpio_claim_output(self._lgpio_handle, self.laser_pin, 0)
                    self._use_lgpio = True
                    default_state = laser_config.get("default_state", "OFF")
                    if default_state.upper() == "ON":
                        _lgpio.gpio_write(self._lgpio_handle, self.laser_pin, 1)
                    logger.info("Laser using lgpio (Bookworm/Pi 5 compatible)")
            except Exception as e:
                logger.warning(f"lgpio init failed, trying RPi.GPIO: {e}")
                if self._lgpio_handle is not None and self._lgpio_handle >= 0:
                    try:
                        _lgpio.gpiochip_close(self._lgpio_handle)
                    except Exception:
                        pass
                    self._lgpio_handle = None
                self._use_lgpio = False

        if not self._use_lgpio and _GPIO is not None:
            try:
                _GPIO.setmode(_GPIO.BCM)
                _GPIO.setwarnings(False)
                try:
                    _GPIO.cleanup(self.laser_pin)
                except Exception:
                    pass
                _GPIO.setup(self.laser_pin, _GPIO.OUT)
                default_state = laser_config.get("default_state", "OFF")
                initial = _GPIO.LOW if default_state.upper() == "OFF" else _GPIO.HIGH
                _GPIO.output(self.laser_pin, initial)
                self.ON = _GPIO.HIGH
                self.OFF = _GPIO.LOW
            except Exception as e:
                raise RuntimeError(f"Failed to initialize laser on GPIO {self.laser_pin}: {e}") from e
        elif not self._use_lgpio:
            raise RuntimeError(
                "No GPIO library available. On Bookworm/Pi 5 install: sudo apt install python3-lgpio"
            )
        else:
            self.ON = 1
            self.OFF = 0

    def __del__(self) -> None:
        """Release lgpio handle so the pin is not left claimed."""
        if getattr(self, "_use_lgpio", False) and getattr(self, "_lgpio_handle", None) is not None:
            try:
                if _lgpio is not None and self._lgpio_handle >= 0:
                    _lgpio.gpio_write(self._lgpio_handle, self.laser_pin, 0)
                    _lgpio.gpiochip_close(self._lgpio_handle)
            except Exception:
                pass

    def switch(self, state: Optional[int] = None) -> None:
        """Turn laser ON or OFF. state: 1/ON or 0/OFF (or GPIO.HIGH/GPIO.LOW when using RPi.GPIO)."""
        if state is None:
            raise ValueError("Laser state must be specified (1/ON or 0/OFF)")

        is_on = bool(state)  # 1, GPIO.HIGH, etc. -> True; 0, GPIO.LOW -> False

        if self._use_lgpio:
            _lgpio.gpio_write(self._lgpio_handle, self.laser_pin, 1 if is_on else 0)
        else:
            if state not in (self.ON, self.OFF, getattr(_GPIO, "HIGH", 1), getattr(_GPIO, "LOW", 0)):
                raise ValueError(f"Invalid laser state: {state}")
            _GPIO.output(self.laser_pin, self.ON if is_on else self.OFF)

        logger.info("Laser switched to %s", "ON" if is_on else "OFF")
