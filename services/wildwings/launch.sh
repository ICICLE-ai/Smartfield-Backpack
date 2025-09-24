#!/bin/bash

# Initialize Conda for the shell
source ~/miniconda3/etc/profile.d/conda.sh

# Activate the Conda environment
conda activate wildwing

# Generate a timestamp
timestamp=$(date +"%Y%m%d_%H%M%S")

# Create main mission directory if it doesn't exist
mkdir -p "mission"

# Create timestamped output directory
output_dir="mission/mission_record_$timestamp"
mkdir -p "$output_dir"

# Ensure logs directory exists
mkdir -p "logs"

# Log start of mission
echo "$(date): Starting WildWings mission with timestamp $timestamp" | tee -a logs/wildwings.txt

# Run the Python script with live output to wildwings.txt
python3 controller.py "$output_dir" 2>&1 | tee -a logs/wildwings.txt

# Log completion
echo "$(date): WildWings mission completed" | tee -a logs/wildwings.txt