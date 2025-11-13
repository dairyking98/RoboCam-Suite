#!/bin/bash
# Quick fix script for missing system dependencies
# Run this if setup.sh failed due to missing libcap-dev or other build dependencies

echo "RoboCam-Suite Dependency Fix Script"
echo "==================================="
echo ""

# Install required system dependencies
echo "Installing system dependencies..."
sudo apt-get update
sudo apt-get install -y libcap-dev python3-dev build-essential

echo ""
echo "System dependencies installed."
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Virtual environment not found. Please run ./setup.sh first."
    exit 1
fi

# Activate virtual environment and reinstall Python packages
echo "Activating virtual environment and reinstalling Python packages..."
source venv/bin/activate

echo "Upgrading pip..."
pip install --upgrade pip

echo ""
echo "Reinstalling requirements..."
pip install -r requirements.txt

echo ""
echo "Verifying installation..."
if pip show picamera2 &>/dev/null && pip show pyserial &>/dev/null; then
    echo "✓ picamera2 and pyserial are installed successfully!"
    echo ""
    echo "You can now run:"
    echo "  ./start_calibrate.sh"
else
    echo "✗ Some packages are still missing. Please check the error messages above."
    exit 1
fi

