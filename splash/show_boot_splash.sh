#!/bin/bash
# NuNet Boot Splash Launcher
# This script launches the NuNet boot splash screen

# Check if splash has already been shown in this session
if [[ -n "$NUNET_SPLASH_SHOWN" ]]; then
    exit 0
fi

# Set flag to prevent showing splash multiple times
export NUNET_SPLASH_SHOWN=1

# Check if we're in a terminal (TTY) - this should work for console login
if [[ -t 1 ]]; then
    # Launch the Python splash screen
    python3 /home/ubuntu/nunet/appliance/splash/nunet_boot_splash.py 2>/dev/null || true
fi
