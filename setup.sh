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

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    echo "Virtual environment created."
else
    echo "Virtual environment already exists."
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
    pip install -r requirements.txt
    echo "Dependencies installed."
else
    echo "Warning: requirements.txt not found. Skipping dependency installation."
fi

echo ""

# Create configuration directories
echo "Creating configuration directories..."
mkdir -p config/motion_configs
mkdir -p config/templates
mkdir -p docs
echo "Configuration directories created."

echo ""

# Create default motion configuration files if they don't exist
if [ ! -f "config/motion_configs/default_motion.json" ]; then
    echo "Creating default motion configuration..."
    cat > config/motion_configs/default_motion.json << 'EOF'
{
  "preliminary_feedrate": 2000,
  "preliminary_acceleration": 1000,
  "between_wells_feedrate": 1500,
  "between_wells_acceleration": 800,
  "description": "Default motion profile - balanced speed and precision",
  "author": "RoboCam-Suite",
  "created": "2025-01-01"
}
EOF
    echo "Default motion configuration created."
fi

if [ ! -f "config/motion_configs/fast_motion.json" ]; then
    echo "Creating fast motion configuration..."
    cat > config/motion_configs/fast_motion.json << 'EOF'
{
  "preliminary_feedrate": 3000,
  "preliminary_acceleration": 1500,
  "between_wells_feedrate": 2500,
  "between_wells_acceleration": 1200,
  "description": "Fast motion profile - high speed and acceleration",
  "author": "RoboCam-Suite",
  "created": "2025-01-01"
}
EOF
    echo "Fast motion configuration created."
fi

if [ ! -f "config/motion_configs/precise_motion.json" ]; then
    echo "Creating precise motion configuration..."
    cat > config/motion_configs/precise_motion.json << 'EOF'
{
  "preliminary_feedrate": 1000,
  "preliminary_acceleration": 500,
  "between_wells_feedrate": 800,
  "between_wells_acceleration": 400,
  "description": "Precise motion profile - lower speed for accuracy",
  "author": "RoboCam-Suite",
  "created": "2025-01-01"
}
EOF
    echo "Precise motion configuration created."
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

echo "Setup complete!"
echo ""
echo "To activate the virtual environment, run:"
echo "  source venv/bin/activate"
echo ""
echo "To start the calibration application:"
echo "  ./start_calibrate.sh"
echo ""
echo "To start the experiment application:"
echo "  ./start_experiment.sh"
echo ""

