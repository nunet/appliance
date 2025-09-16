#!/bin/bash
export DMS_PASSPHRASE=$(keyctl pipe $(keyctl request user dms_passphrase) 2>/dev/null)

# Directory for logs
log_dir="$HOME/nunet/appliance/peer_logs"
mkdir -p "$log_dir"

# Log file (CSV format)
log_file="$log_dir/peer_rtt_scores.csv"

# Check if log file exists; if not, add header
if [[ ! -f "$log_file" ]]; then
    echo "Timestamp,Peer,RTT,Score,Penalty,IPColoc,AppScore,Error" > "$log_file"
fi

# Temporary files
ping_temp=$(mktemp)
score_temp=$(mktemp)
merged_file=$(mktemp)

# Get current timestamp
timestamp=$(date +"%Y-%m-%d %H:%M:%S")

# Fetch list of peers
peers=$(nunet -c dms actor cmd /dms/node/peers/list | jq -r '.Peers[]' | grep '^12D')

# Initialize counters
total_peers=0
valid_peers=0
low_latency_peers=0
local_peers=0

# Loop through each peer and ping it
for peer in $peers; do
    ((total_peers++))
    
    # Run the ping command and capture output
    output=$(nunet -c dms actor cmd /dms/node/peers/ping --host "$peer")

    # Extract RTT and Error message
    rtt=$(echo "$output" | jq -r '.RTT // 0')
    error=$(echo "$output" | jq -r '.Error // "None"')

    # Count valid peers (RTT > 0)
    if [[ "$rtt" -gt 0 ]]; then
        ((valid_peers++))
    fi

    # Count low latency peers (RTT < 30ms)
    if [[ "$rtt" -gt 0 && "$rtt" -lt 30 ]]; then
        ((low_latency_peers++))
    fi

    # Count local peers (RTT < 5ms)
    if [[ "$rtt" -gt 0 && "$rtt" -lt 5 ]]; then
        ((local_peers++))
    fi

    # Store ping results in temp file
    echo "$peer $rtt $error" >> "$ping_temp"
done

# Fetch peer scores
peer_scores=$(nunet -c dms actor cmd /dms/node/peers/score | jq -r '.Score')

# Extract and store scores
echo "$peer_scores" | jq -r 'to_entries[] | "\(.key) \(.value.Score) \(.value.BehaviourPenalty) \(.value.IPColocationFactor) \(.value.AppSpecificScore)"' > "$score_temp"

# Count peers with behaviour penalties
high_penalty_count=$(awk '$3 > 0' "$score_temp" | wc -l)

# Merge ping results and score results based on Peer ID
join -j 1 <(sort "$ping_temp") <(sort "$score_temp") > "$merged_file"

# Append results to CSV file with timestamp
while IFS= read -r line; do
    peer=$(echo "$line" | awk '{print $1}')
    rtt=$(echo "$line" | awk '{print $2}')
    score=$(echo "$line" | awk '{print $3}')
    penalty=$(echo "$line" | awk '{print $4}')
    ipcoloc=$(echo "$line" | awk '{print $5}')
    appscore=$(echo "$line" | awk '{print $6}')
    error=$(echo "$line" | awk '{print $7}')

    echo "$timestamp,$peer,$rtt,$score,$penalty,$ipcoloc,$appscore,$error" >> "$log_file"
done < "$merged_file"

# Cleanup
rm "$ping_temp" "$score_temp" "$merged_file"

echo "✅ Data collection complete. Logged to: $log_file"
