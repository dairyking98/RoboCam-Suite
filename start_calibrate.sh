#!/bin/bash
# RoboCam-Suite Calibration Application Launcher

set -e  # Exit on error

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Error: Virtual environment not found. Please run ./setup.sh first."
    exit 1
fi

# Activate virtual environment
source venv/bin/activate

# Check if calibrate.py exists
if [ ! -f "calibrate.py" ]; then
    echo "Error: calibrate.py not found in current directory."
    exit 1
fi

# Create log directory if it doesn't exist
mkdir -p logs

# Run the calibration application
echo "Starting RoboCam-Suite Calibration Application..."
echo "Log file: logs/calibrate_$(date +%Y%m%d_%H%M%S).log"
echo ""

# Pass through all command-line arguments (e.g., --simulate, --backend)
python calibrate.py "$@" 2>&1 | tee "logs/calibrate_$(date +%Y%m%d_%H%M%S).log"

# Deactivate virtual environment on exit
deactivate

