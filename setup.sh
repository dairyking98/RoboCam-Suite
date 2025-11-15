#!/bin/bash
# RoboCam-Suite Setup Script
# Creates virtual environment and installs dependencies

set -e  # Exit on error

echo "RoboCam-Suite Setup Script"
echo "=========================="
echo ""

# Check for Python 3
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed or not in PATH"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
echo "Found Python: $PYTHON_VERSION"

# Check Python version (3.7+)
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d'.' -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d'.' -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 7 ]); then
    echo "Error: Python 3.7 or higher is required. Found: $PYTHON_VERSION"
    exit 1
fi

echo "Python version check passed."
echo ""

# Check for and install system dependencies
echo "Checking for system dependencies..."
MISSING_DEPS=()

# Check for python3-libcamera (required for picamera2)
if ! dpkg -l | grep -q "^ii.*python3-libcamera"; then
    MISSING_DEPS+=("python3-libcamera")
fi

# Check for libcap-dev (required for python-prctl)
if ! dpkg -l | grep -q "^ii.*libcap-dev"; then
    MISSING_DEPS+=("libcap-dev")
fi

# Check for other common build dependencies
if ! dpkg -l | grep -q "^ii.*python3-dev"; then
    MISSING_DEPS+=("python3-dev")
fi

if ! dpkg -l | grep -q "^ii.*build-essential"; then
    MISSING_DEPS+=("build-essential")
fi

if [ ${#MISSING_DEPS[@]} -gt 0 ]; then
    echo "Missing system dependencies detected: ${MISSING_DEPS[*]}"
    echo "These are required for:"
    echo "  - python3-libcamera: Required for picamera2 (Raspberry Pi camera support)"
    echo "  - libcap-dev, python3-dev, build-essential: Required to build Python packages"
    echo ""
    echo "Please install them before continuing:"
    echo "  sudo apt-get update"
    echo "  sudo apt-get install -y ${MISSING_DEPS[*]}"
    echo ""
    echo "Attempting to install automatically (requires sudo)..."
    if sudo apt-get update && sudo apt-get install -y "${MISSING_DEPS[@]}" 2>/dev/null; then
        echo "System dependencies installed successfully."
    else
        echo ""
        echo "ERROR: Could not install system dependencies automatically."
        echo "Please run the following commands manually:"
        echo "  sudo apt-get update"
        echo "  sudo apt-get install -y ${MISSING_DEPS[*]}"
        echo ""
        echo "Then re-run this setup script."
        exit 1
    fi
else
    echo "System dependencies check passed."
fi

echo ""

# Create virtual environment with system site packages
# This allows access to system-installed packages like python3-libcamera
if [ ! -d "venv" ]; then
    echo "Creating virtual environment (with system site packages)..."
    python3 -m venv --system-site-packages venv
    echo "Virtual environment created."
else
    echo "Virtual environment already exists."
    echo "Note: If you're having issues with libcamera, you may need to recreate the venv with:"
    echo "  rm -rf venv && python3 -m venv --system-site-packages venv"
fi

echo ""

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

echo ""

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip

echo ""

# Install dependencies
if [ -f "requirements.txt" ]; then
    echo "Installing dependencies from requirements.txt..."
    # Try to install dependencies, but don't exit on error
    # This allows partial installation if some packages fail
    set +e  # Temporarily disable exit on error
    pip install -r requirements.txt
    PIP_EXIT_CODE=$?
    set -e  # Re-enable exit on error
    
    if [ $PIP_EXIT_CODE -eq 0 ]; then
        echo "Dependencies installed successfully."
    else
        echo ""
        echo "Warning: Some dependencies failed to install."
        echo "This may be due to missing system packages."
        echo ""
        echo "Common solutions:"
        echo "  1. Install missing system dependencies (see above)"
        echo "  2. Try installing dependencies manually:"
        echo "     source venv/bin/activate"
        echo "     pip install -r requirements.txt"
        echo ""
        echo "Checking which packages were installed..."
        pip list | grep -E "(picamera2|pyserial)" || echo "Critical packages may be missing."
    fi
else
    echo "Warning: requirements.txt not found. Skipping dependency installation."
fi

echo ""

# Create configuration directories
echo "Creating configuration directories..."
mkdir -p calibrations
mkdir -p experiments
mkdir -p config/templates
mkdir -p docs
echo "Configuration directories created."

echo ""

# Create motion configuration file with all profiles if it doesn't exist
if [ ! -f "config/motion_config.json" ]; then
    echo "Creating motion configuration file with profiles..."
    cat > config/motion_config.json << 'EOF'
{
  "default": {
    "name": "Default Profile",
    "description": "Balanced speed and precision for general use",
    "preliminary": {
      "feedrate": 3000,
      "acceleration": 500
    },
    "between_wells": {
      "feedrate": 1200,
      "acceleration": 300
    }
  },
  "precise": {
    "name": "Precise Profile",
    "description": "Lower speed and acceleration for maximum precision",
    "preliminary": {
      "feedrate": 2000,
      "acceleration": 300
    },
    "between_wells": {
      "feedrate": 3000,
      "acceleration": 500
    }
  },
  "fast": {
    "name": "Fast Profile",
    "description": "Maximum speed for rapid well-to-well movements",
    "preliminary": {
      "feedrate": 5000,
      "acceleration": 1000
    },
    "between_wells": {
      "feedrate": 8000,
      "acceleration": 1500
    }
  }
}
EOF
    echo "Motion configuration file created with default, precise, and fast profiles."
fi

echo ""

# Verify critical packages are installed
echo "Verifying installation..."
CRITICAL_PACKAGES=("picamera2" "pyserial")
MISSING_PACKAGES=()

for package in "${CRITICAL_PACKAGES[@]}"; do
    if ! pip show "$package" &>/dev/null; then
        MISSING_PACKAGES+=("$package")
    fi
done

if [ ${#MISSING_PACKAGES[@]} -gt 0 ]; then
    echo ""
    echo "WARNING: The following critical packages are missing: ${MISSING_PACKAGES[*]}"
    echo "Installation may have failed. Please check the error messages above."
    echo ""
    echo "To fix this, try:"
    echo "  1. Ensure system dependencies are installed (libcap-dev, python3-dev, build-essential)"
    echo "  2. Activate the virtual environment: source venv/bin/activate"
    echo "  3. Reinstall: pip install -r requirements.txt"
    echo ""
else
    echo "Critical packages verified: ${CRITICAL_PACKAGES[*]}"
fi

echo ""

# Check for hardware (optional, inform user)
echo "Hardware Setup Checklist:"
echo "  - Raspberry Pi Camera: Check connection and enable in raspi-config"
echo "  - 3D Printer: Check USB serial connection"
echo "  - GPIO Laser: Check connection to GPIO pin (default: GPIO 21)"
echo "  - Serial Port Permissions: Add user to dialout group if needed"
echo "    sudo usermod -a -G dialout \$USER"
echo "  - GPIO Permissions: Add user to gpio group if needed"
echo "    sudo usermod -a -G gpio \$USER"
echo ""

if [ ${#MISSING_PACKAGES[@]} -eq 0 ]; then
    echo "Setup complete!"
else
    echo "Setup completed with warnings. Please address missing packages before use."
fi
echo ""
echo "To activate the virtual environment, run:"
echo "  source venv/bin/activate"
echo ""
echo "To start the calibration application:"
echo "  ./start_calibrate.sh"
echo ""
echo "To start the preview application:"
echo "  ./start_preview.sh"
echo ""
echo "To start the experiment application:"
echo "  ./start_experiment.sh"
echo ""

