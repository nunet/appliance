#!/bin/bash
# NuNet Boot Splash Launcher
# This script launches the NuNet boot splash screen

# Check if we're in an interactive shell
if [[ $- == *i* ]]; then
    # Check if this is a login shell (not a subshell)
    if [[ -z "$NUNET_SPLASH_SHOWN" ]]; then
        # Set flag to prevent showing splash multiple times
        export NUNET_SPLASH_SHOWN=1
        
        # Check if we're in a terminal (not SSH without PTY)
        if [[ -t 0 && -t 1 ]]; then
            # Launch the Python splash screen
            python3 /home/ubuntu/nunet/appliance/splash/nunet_boot_splash.py
        fi
    fi
fi
