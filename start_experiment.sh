#!/bin/bash
# RoboCam-Suite Experiment Application Launcher

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

# Check if experiment.py exists
if [ ! -f "experiment.py" ]; then
    echo "Error: experiment.py not found in current directory."
    exit 1
fi

# Create log directory if it doesn't exist
mkdir -p logs

# Run the experiment application
echo "Starting RoboCam-Suite Experiment Application..."
echo "Log file: logs/experiment_$(date +%Y%m%d_%H%M%S).log"
echo ""

# Pass through all command-line arguments (e.g., --simulate_3d, --simulate_cam)
# Examples:
#   ./start_experiment.sh --simulate_3d
#   ./start_experiment.sh --simulate_cam
#   ./start_experiment.sh --simulate_3d --simulate_cam
python experiment.py "$@" 2>&1 | tee "logs/experiment_$(date +%Y%m%d_%H%M%S).log"

# Deactivate virtual environment on exit
deactivate

