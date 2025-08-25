#!/bin/bash

# Docker launch script for WildWings
# This script handles the conda environment and display setup within Docker

# Setup X11 forwarding automatically
export DISPLAY=${DISPLAY:-:99}

# Activate conda environment
source /opt/conda/etc/profile.d/conda.sh
conda activate wildwing

# Generate a timestamp
timestamp=$(date +"%Y%m%d_%H%M%S")

# Create file to save tracking results
output_dir="missions/mission_record_$timestamp"

# Create the output directory if it does not exist
mkdir -p "$output_dir"
mkdir -p "logs"

# Copy any existing mission data from old volume location if it exists
if [ -d "/app/missions" ] && [ ! "$(ls -A /app/missions 2>/dev/null)" ]; then
    echo "Mission directory is empty or doesn't exist"
fi


# Run the Python script and save the output to a log file
python controller.py "$output_dir" > "logs/output_$timestamp.log" 2>&1