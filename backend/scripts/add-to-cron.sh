#!/bin/bash

# Script path
SCRIPT_PATH="$HOME/menu/scripts/collect-peer-data.sh"

# Check if the script exists
if [[ ! -f "$SCRIPT_PATH" ]]; then
    echo "❌ Error: Script not found at $SCRIPT_PATH"
    exit 1
fi

# Cron job to run every 1 minutes
CRON_JOB="* * * * * /usr/bin/keyctl link @u @s && $SCRIPT_PATH >> /tmp/collect-peer-data.log 2>&1"

# Check if the cron job already exists
(crontab -l 2>/dev/null | grep -Fq "$SCRIPT_PATH") && echo "✅ Script is already scheduled in cron." && exit 0

# Add the new cron job
(crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -

echo "✅ Successfully added script to cron."
