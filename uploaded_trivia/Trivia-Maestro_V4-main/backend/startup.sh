#!/bin/bash
# Startup script for Story Generator backend
# Ensures required system dependencies are installed

echo "=== Story Generator Startup ==="

# Install FFmpeg if not present
if ! command -v ffmpeg &> /dev/null; then
    echo "Installing FFmpeg..."
    apt-get update -qq && apt-get install -y ffmpeg
fi

# Install Lemonada font if not present
if [ ! -f "/usr/share/fonts/opentype/lemonada/Lemonada-Bold.otf" ]; then
    echo "Installing Lemonada font..."
    apt-get install -y fonts-lemonada
    fc-cache -fv
fi

echo "Dependencies verified. Starting backend..."
exec "$@"
