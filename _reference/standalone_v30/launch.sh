#!/bin/bash
echo "🚀 BIGHat Standalone Launcher"
echo "Checking for dependencies..."
pip install fastapi uvicorn pydantic 
echo "Starting BIGHat System..."
cd backend
python3 main.py
