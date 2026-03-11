#!/bin/bash

# Directory for logs
log_dir="$HOME/nunet/appliance/peer_logs"
log_file="$log_dir/peer_rtt_scores.csv"

# Ensure log file exists
if [[ ! -f "$log_file" ]]; then
    echo "❌ Error: Log file not found. Run collect_peer_data.sh first."
    exit 1
fi

# Display header
echo -e "\n🔍 Showing the most recent peer data:"
printf "%-50s %-10s %-10s %-10s %-10s %-10s %-10s\n" "Peer" "RTT(ms)" "Score" "Penalty" "IPColoc" "AppScore" "Error"
printf "%-50s %-10s %-10s %-10s %-10s %-10s %-10s\n" "--------------------------------------------------" "--------" "--------" "--------" "--------" "--------" "--------"

# Display most recent data (last recorded timestamp)
latest_timestamp=$(tail -n 1 "$log_file" | awk -F, '{print $1}')
grep "$latest_timestamp" "$log_file" | sort -t, -k3 -n | awk -F, '{ printf "%-50s %-10s %-10s %-10s %-10s %-10s %-10s\n", $2, $3, $4, $5, $6, $7, $8 }'

# Display summary statistics
total_peers=$(grep "$latest_timestamp" "$log_file" | wc -l)
valid_peers=$(grep "$latest_timestamp" "$log_file" | awk -F, '$3 > 0' | wc -l)
low_latency_peers=$(grep "$latest_timestamp" "$log_file" | awk -F, '$3 > 0 && $3 < 30' | wc -l)
local_peers=$(grep "$latest_timestamp" "$log_file" | awk -F, '$3 > 0 && $3 < 5' | wc -l)
high_penalty_count=$(grep "$latest_timestamp" "$log_file" | awk -F, '$5 > 0' | wc -l)

echo -e "\n📊 Summary:"
echo "Total Peers: $total_peers"
echo "Valid Peers (RTT > 0): $valid_peers"
echo "Low Latency Peers (RTT < 30ms): $low_latency_peers"
echo "Local Peers (RTT < 5ms): $local_peers"
echo "Peers with Behaviour Penalties: $high_penalty_count"

echo -e "\n📂 Data source: $log_file"

# --------------------------
# 📊 Live RTT Graph with `gnuplot`
# --------------------------

# Filter data for the last hour
log_filtered="$log_dir/gnuplot_rtt_data.txt"
tail -n 60 "$log_file" | awk -F, '{print $1, $3}' > "$log_filtered"

# Launch gnuplot for live RTT visualization
gnuplot -persist <<-EOF
    set title "Peer RTT Over Time (Last Hour)"
    set xdata time
    set timefmt "%Y-%m-%d %H:%M:%S"
    set format x "%H:%M"
    set xlabel "Time (HH:MM)"
    set ylabel "RTT (ms)"
    set grid

    # Set X-axis to 1 hour with 1-minute intervals
    now = system("date +'%Y-%m-%d %H:%M:%S'")
    set xrange [strptime("%Y-%m-%d %H:%M:%S", now)-3600:strptime("%Y-%m-%d %H:%M:%S", now)]
    set xtics 300  # Set X-axis ticks every 5 minutes

    # Auto-scale Y-axis based on data
    stats "$log_filtered" using 2 nooutput
    set yrange [STATS_min_y:STATS_max_y]
    set ytics auto  # Enable automatic Y-axis ticks

    set term dumb 100 30
    plot "$log_filtered" using 1:2 with lines title "RTT (ms)"
EOF
