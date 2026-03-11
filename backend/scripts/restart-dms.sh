#!/bin/bash

export DMS_PASSPHRASE=$(keyctl pipe $(keyctl request user dms_passphrase) 2>/dev/null)
export EDITOR=nano
export GOLOG_LOG_LEVEL="debug"
PID_FILE="$HOME/nunet_dms.pid"
LOG_FILE="$HOME/nunet_dms.log"
DMS_COMMAND="nunet run -c dms"

echo "Checking for existing nunet process..."

# Step 1: Check if the PID file exists and kill the process
if [[ -f "$PID_FILE" ]]; then
    PID=$(cat "$PID_FILE")
    
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "Found running nunet process with PID: $PID, stopping it..."
        kill "$PID"
        sleep 2  # Allow process to terminate
    else
        echo "Process $PID not found, removing stale PID file."
    fi
    
    rm -f "$PID_FILE"
else
    echo "No PID file found, skipping direct process kill."
fi

# Step 2: Check for any other instances of `nunet` and kill them
echo "Checking for any other running nunet processes..."
PIDS=$(pgrep -f "nunet run -c dms")

if [[ -n "$PIDS" ]]; then
    echo "Killing additional nunet processes: $PIDS"
    kill $PIDS
    sleep 2  # Allow processes to terminate
else
    echo "No other nunet processes found."
fi

# Step 3: Start `nunet-dms` in the background and save its PID
echo "Starting nunet-dms in the background..."
nohup $DMS_COMMAND > "$LOG_FILE" 2>&1 & echo $! > "$PID_FILE"

echo "nunet-dms started successfully with PID: $(cat $PID_FILE)"
