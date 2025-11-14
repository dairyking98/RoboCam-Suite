#!/bin/bash
# RoboCam-Suite Preview Application Launcher

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

# Check if preview.py exists
if [ ! -f "preview.py" ]; then
    echo "Error: preview.py not found in current directory."
    exit 1
fi

# Create log directory if it doesn't exist
mkdir -p logs

# Run the preview application
echo "Starting RoboCam-Suite Preview Application..."
echo "Log file: logs/preview_$(date +%Y%m%d_%H%M%S).log"
echo ""

python preview.py 2>&1 | tee "logs/preview_$(date +%Y%m%d_%H%M%S).log"

# Deactivate virtual environment on exit
deactivate

