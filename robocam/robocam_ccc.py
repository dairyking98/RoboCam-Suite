"""
RoboCam Module - 3D Printer Control via G-code

This module provides control of a 3D printer (used as a positioning stage) via
G-code commands over serial communication. This is the preferred implementation
as it includes M400 wait commands for reliable movement completion.

Author: RoboCam-Suite
"""

import serial
import serial.tools.list_ports
import time
import sys
import re
from typing import Optional, Tuple
from picamera2 import Picamera2
from .config import get_config, Config
from .logging_config import get_logger

logger = get_logger(__name__)


class RoboCam:
    """
    Control interface for 3D printer used as robotic positioning stage.
    
    This class communicates with a 3D printer via serial G-code commands to control
    the X, Y, Z positioning of the print head (which holds the camera). This is the
    preferred implementation as it includes M400 wait commands for reliable operation.
    
    Attributes:
        baud_rate (int): Serial communication baud rate
        printer_on_serial (serial.Serial): Serial connection to printer
        X (float): Current X position in mm
        Y (float): Current Y position in mm
        Z (float): Current Z position in mm
    """
    
    def __init__(self, baudrate: Optional[int] = None, config: Optional[Config] = None) -> None:
        """
        Initialize RoboCam and connect to printer.
        
        Args:
            baudrate: Serial communication baud rate. If None, uses config default.
            config: Configuration object. If None, uses global config.
            
        Note:
            Automatically finds and connects to USB serial port.
            Sends M105 command to announce control and updates position.
            
        Raises:
            ConnectionError: If printer connection fails
            serial.SerialException: If serial port cannot be opened
        """
        # Load configuration
        self.config: Config = config if config else get_config()
        printer_config = self.config.get_printer_config()
        
        # Printer startup and settings
        self.baud_rate: int = baudrate if baudrate is not None else printer_config.get("baudrate", 115200)
        self.timeout: float = printer_config.get("timeout", 1.0)
        self.command_delay: float = printer_config.get("command_delay", 0.1)
        self.position_update_delay: float = printer_config.get("position_update_delay", 0.1)
        self.connection_retry_delay: float = printer_config.get("connection_retry_delay", 2.0)
        self.max_retries: int = printer_config.get("max_retries", 5)
        
        # Initialize position tracking
        self.X: Optional[float] = None
        self.Y: Optional[float] = None
        self.Z: Optional[float] = None
        self.printer_on_serial: Optional[serial.Serial] = None
        
        # Connect to printer
        try:
            serial_port = self.find_serial_port()
            if serial_port:
                self.printer_on_serial = self.wait_for_connection(serial_port)
            else:
                raise ConnectionError("No serial port found. Check USB connection to printer.")
            
            # Announce control
            self.send_gcode("M105")  # creality ender 5 s1, to announce control via serial
            
            # Update position
            self.X, self.Y, self.Z = self.update_current_position()
        except Exception as e:
            raise ConnectionError(f"Failed to initialize RoboCam: {e}") from e

    def send_gcode(self, command: str, timeout: Optional[float] = None) -> None:
        """
        Send a G-code command to the printer and wait for acknowledgment.
        
        Args:
            command: G-code command string to send (e.g., "G28", "G0 X10 Y20")
            timeout: Timeout in seconds. If None, uses config timeout.
            
        Raises:
            ConnectionError: If printer is not connected
            serial.SerialException: If serial communication fails
            TimeoutError: If printer doesn't respond within timeout
            
        Note:
            Waits for "ok" response from printer before returning.
            Raises exception if printer responds with "error".
        """
        if self.printer_on_serial is None:
            raise ConnectionError("Printer not connected. Cannot send G-code command.")
        
        if timeout is None:
            timeout = self.timeout
        
        logger.debug(f'Sending G-code command: "{command}"')
        
        try:
            self.printer_on_serial.write((command + '\n').encode('utf-8'))
            time.sleep(self.command_delay)  # Initial delay for command processing
            
            start_time = time.time()
            while True:
                if time.time() - start_time > timeout:
                    raise TimeoutError(f"G-code command '{command}' timed out after {timeout}s")
                
                if self.printer_on_serial.in_waiting > 0:
                    response = self.printer_on_serial.readline().decode('utf-8').strip()
                    logger.debug(f'Printer response: {response}')
                    
                    if "ok" in response.lower():
                        break
                    elif "error" in response.lower():
                        raise RuntimeError(f"Printer error for command '{command}': {response}")
                
                time.sleep(0.01)  # Small delay to avoid busy waiting
                
        except serial.SerialException as e:
            raise ConnectionError(f"Serial communication error: {e}") from e

    def find_serial_port(self) -> Optional[str]:
        """
        Find available USB serial port for printer connection.
        
        Returns:
            Device path of first available USB serial port, or None if none found.
            
        Note:
            Tests each USB port by attempting to open it. Returns the first
            port that can be opened successfully.
            
        Raises:
            serial.SerialException: If port enumeration fails
        """
        try:
            ports = serial.tools.list_ports.comports()
            usb_ports = [port for port in ports if 'USB' in port.description.upper()]
            
            if not usb_ports:
                logger.warning("No USB serial ports found.")
                return None

            for usb_port in usb_ports:
                try:
                    ser = serial.Serial(usb_port.device, self.baud_rate, timeout=self.timeout)
                    ser.close()  # Close the port now that we know it works
                    logger.info(f"Selected port: {usb_port.device} - {usb_port.description}")
                    return usb_port.device
                except serial.SerialException as e:
                    logger.debug(f"Failed to connect on {usb_port.device}: {e}")
                    continue

            logger.warning("No available ports responded.")
            return None
            
        except Exception as e:
            logger.error(f"Error finding serial port: {e}")
            return None

    def wait_for_connection(self, serial_port: str) -> serial.Serial:
        """
        Attempt to open a serial connection and wait until it is established.
        
        Args:
            serial_port: Device path of serial port to connect to
            
        Returns:
            Serial connection object
            
        Raises:
            ConnectionError: If connection fails after max retries
            serial.SerialException: If serial port cannot be opened
            
        Note:
            Retries connection with configurable delay and max retries.
            Waits 1 second after connection for printer to initialize.
        """
        retries = 0
        while retries < self.max_retries:
            try:
                self.printer_on_serial = serial.Serial(
                    serial_port, 
                    self.baud_rate, 
                    timeout=self.timeout
                )
                logger.info(f"Connected to {serial_port} at {self.baud_rate} baud. Allow 1 seconds for printer to load.")
                time.sleep(1)
                # Dump printer output on startup
                self.dump_printer_output()
                return self.printer_on_serial
            except serial.SerialException as e:
                retries += 1
                if retries >= self.max_retries:
                    raise ConnectionError(
                        f"Failed to connect to {serial_port} after {self.max_retries} attempts: {e}"
                    ) from e
                logger.info(f"Waiting for connection on {serial_port}... (attempt {retries}/{self.max_retries})")
                time.sleep(self.connection_retry_delay)
        
        raise ConnectionError(f"Failed to connect to {serial_port} after {self.max_retries} attempts")
                
    def dump_printer_output(self) -> None:
        """
        Read and print all pending output from printer.
        
        Note:
            Clears the serial buffer by reading all available data.
            Useful after connection to clear startup messages.
        """
        while self.printer_on_serial.in_waiting > 0:  # Check if there's data waiting to be read
            response = self.printer_on_serial.readline().decode('utf-8').strip()
            logger.debug(f'Printer output, dumping: {response}')
    
    def set_acceleration(self, acceleration: float) -> None:
        """
        Set printer acceleration in mm/s².
        
        Args:
            acceleration: Acceleration value in mm/s² (must be > 0)
            
        Raises:
            ConnectionError: If printer is not connected
            ValueError: If acceleration is invalid
            RuntimeError: If command fails
            
        Note:
            Sends M204 S<acceleration> command to set acceleration.
            Some printers may use M204 P<acceleration> for print acceleration.
            This uses S parameter for general acceleration.
        """
        if self.printer_on_serial is None:
            raise ConnectionError("Printer not connected. Cannot set acceleration.")
        
        if acceleration <= 0:
            raise ValueError(f"Invalid acceleration: {acceleration} (must be > 0)")
        
        try:
            # M204 S sets acceleration in mm/s²
            # Some firmware may use M204 P for print acceleration, S for travel
            # Using S for general acceleration setting
            self.send_gcode(f"M204 S{acceleration}")
            logger.info(f'Acceleration set to {acceleration} mm/s²')
        except Exception as e:
            raise RuntimeError(f"Failed to set acceleration: {e}") from e
                
    def home(self) -> None:
        """
        Home the printer to origin (0, 0, 0).
        
        Raises:
            ConnectionError: If printer is not connected
            RuntimeError: If homing command fails
            TimeoutError: If homing times out
            
        Note:
            Sends G28 command which homes all axes.
            Updates position after homing completes.
        """
        logger.info('Homing Printer, please wait for the countdown to complete')
        try:
            self.send_gcode('G28', timeout=self.timeout * 5)  # Homing takes longer, use 5x timeout
            # Update position after homing
            self.X, self.Y, self.Z = self.update_current_position()
            logger.info(f"Printer homed. Reset positions to X: {self.X}, Y: {self.Y}, Z: {self.Z}")
        except Exception as e:
            raise RuntimeError(f"Homing failed: {e}") from e

    def update_current_position(self) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        """
        Query printer for current position and update internal state.
        
        Returns:
            Tuple of (X, Y, Z) positions in mm, or (None, None, None) if unavailable.
            
        Raises:
            ConnectionError: If printer is not connected
            TimeoutError: If position query times out
            ValueError: If position cannot be parsed
            
        Note:
            Sends M114 command to get current position.
            Parses response and updates self.X, self.Y, self.Z.
        """
        if self.printer_on_serial is None:
            raise ConnectionError("Printer not connected. Cannot update position.")
        
        logger.debug('Updating current position')
        
        try:
            # Manually sending command because send_gcode dumps all output before "ok" response
            command = "M114"
            self.printer_on_serial.write((command + '\n').encode('utf-8'))
            time.sleep(self.position_update_delay)
            
            # Parse printer's response with timeout
            start_time = time.time()
            response = ""
            while True:
                if time.time() - start_time > self.timeout:
                    raise TimeoutError(f"Position update timed out after {self.timeout}s")
                
                if self.printer_on_serial.in_waiting > 0:
                    response = self.printer_on_serial.readline().decode('utf-8').strip()
                    logger.debug(f'Printer response: {response}')
                    if response.startswith('X:'):
                        break
                
                time.sleep(0.01)
            
            # Parse position values
            position = {}
            matches = re.findall(r'(X|Y|Z):([0-9.-]+)', response)
            collected_axes = set()
            
            for axis, value in matches:
                try:
                    if axis not in collected_axes:
                        position[axis] = float(value)
                        collected_axes.add(axis)
                except ValueError as e:
                    logger.warning(f"Could not parse {axis} value '{value}': {e}")
                    continue
            
            if not position:
                raise ValueError(f"Could not parse position from response: {response}")
                    
            # Save XYZ values
            self.X = position.get('X', None)
            self.Y = position.get('Y', None)
            self.Z = position.get('Z', None)
            
            # Dump remaining printer output
            self.dump_printer_output()
            
            return position.get('X', None), position.get('Y', None), position.get('Z', None)
            
        except serial.SerialException as e:
            raise ConnectionError(f"Serial communication error during position update: {e}") from e
        
    def move_relative(self, X: Optional[float] = None, Y: Optional[float] = None, 
                     Z: Optional[float] = None, speed: Optional[float] = None) -> None:
        """
        Move the print head (camera) by a relative amount in millimeters.
        
        Args:
            X: Relative movement in X direction (mm). None to skip.
            Y: Relative movement in Y direction (mm). None to skip.
            Z: Relative movement in Z direction (mm). None to skip.
            speed: Movement speed in mm/min. None to use default.
            
        Raises:
            ConnectionError: If printer is not connected
            RuntimeError: If movement command fails
            ValueError: If position values are invalid
            
        Note:
            Uses G91 (relative positioning mode).
            Sends M400 to wait for movement completion before returning.
            Updates position after movement.
        """
        if self.printer_on_serial is None:
            raise ConnectionError("Printer not connected. Cannot move.")
        
        # Validate that at least one axis is specified
        if X is None and Y is None and Z is None:
            raise ValueError("At least one axis (X, Y, or Z) must be specified for movement")
        
        logger.debug(f'Relative move to X:{X}, Y:{Y}, Z:{Z}')
        
        try:
            self.send_gcode('G91')
            command = "G0"

            if speed is not None:
                if speed <= 0:
                    raise ValueError(f"Invalid speed: {speed} (must be > 0)")
                command += f" F{speed}"
            if X is not None:
                command += f" X{X}"
            if Y is not None:
                command += f" Y{Y}"
            if Z is not None:
                command += f" Z{Z}"

            self.send_gcode(command)
            self.send_gcode("M400")  # Wait for movement to complete
            self.update_current_position()
        except Exception as e:
            raise RuntimeError(f"Relative movement failed: {e}") from e
            
    def move_absolute(self, X: Optional[float] = None, Y: Optional[float] = None,
                      Z: Optional[float] = None, speed: Optional[float] = None) -> None:
        """
        Move the print head (camera) to an absolute position in millimeters.
        
        Args:
            X: Absolute X position (mm). None to skip.
            Y: Absolute Y position (mm). None to skip.
            Z: Absolute Z position (mm). None to skip.
            speed: Movement speed in mm/min. None to use default.
            
        Raises:
            ConnectionError: If printer is not connected
            RuntimeError: If movement command fails
            ValueError: If position values are invalid
            
        Note:
            Uses G90 (absolute positioning mode).
            Sends M400 to wait for movement completion before returning.
            Updates position after movement.
        """
        if self.printer_on_serial is None:
            raise ConnectionError("Printer not connected. Cannot move.")
        
        # Validate that at least one axis is specified
        if X is None and Y is None and Z is None:
            raise ValueError("At least one axis (X, Y, or Z) must be specified for movement")
        
        logger.debug(f'Absolute move to X:{X}, Y:{Y}, Z:{Z}')
        
        try:
            self.send_gcode('G90')
            command = "G0"

            if speed is not None:
                if speed <= 0:
                    raise ValueError(f"Invalid speed: {speed} (must be > 0)")
                command += f" F{speed}"
            if X is not None:
                command += f" X{X}"
            if Y is not None:
                command += f" Y{Y}"
            if Z is not None:
                command += f" Z{Z}"

            self.send_gcode(command)
            self.send_gcode("M400")  # Wait for movement to complete
            self.update_current_position()
        except Exception as e:
            raise RuntimeError(f"Absolute movement failed: {e}") from e
        
    
