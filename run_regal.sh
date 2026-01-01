#!/bin/bash
echo "Starting Regal Movie Scheduler Setup..."
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi
source venv/bin/activate
echo "Checking dependencies..."
pip install -r requirements.txt
echo "Launching Application..."
streamlit run regal_pro.py