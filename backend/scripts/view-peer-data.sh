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
# 📊 Filter data for last hour
# --------------------------


# Filter data for the last hour
log_filtered="$log_dir/gnuplot_rtt_data.txt"

# Get timestamp for 1 hour ago
one_hour_ago=$(date -d "1 hour ago" +"%Y-%m-%d %H:%M:%S")
#echo "🔍 Debug: one_hour_ago = $one_hour_ago"

# Filter log for  only data within the last hour
awk -F, -v start="$one_hour_ago" '$1 >= start {print $1, $2, $3}' "$log_file" > "$log_filtered"

# Get a list of unique peers from the filtered log file
#echo " Get a list of unique peers from the filtered log file"
peer_list=$(awk  'NR > 1 && $4 > 0 {print $3}' "$log_filtered" | sort -u)

# Check if there are peers in the log
if [[ -z "$peer_list" ]]; then
    echo "❌ No peer data available. Ensure collect-peer-data.sh is running."
    exit 1
fi

echo "🔍 Select a peer to plot RTT over the last hour:"
select selected_peer in $peer_list; do
    if [[ -n "$selected_peer" ]]; then
        break
    else
        echo "❌ Invalid selection. Please choose a valid peer."
    fi
done

echo "✅ Selected Peer: $selected_peer"

# --------------------------
# 📊 Filter Data for Selected Peer
# --------------------------

#echo "🔍 Debug: Filtering log for selected peer..."
#grep "^.*$selected_peer" "$log_filtered"

# Extract data for only the selected peer
grep "^.*$selected_peer" "$log_filtered" > "$log_filtered.peer"

# Ensure the filtered file has data
if [[ ! -s "$log_filtered.peer" ]]; then
    echo "❌ No data available for peer $selected_peer in the last hour."
    exit 1
fi

# Extract min/max RTT values from the filtered log
min_rtt=$(awk '{print $4}' "$log_filtered.peer" | grep '^[0-9]\+$' | sort -n | head -1)
max_rtt=$(awk '{print $4}' "$log_filtered.peer" | grep '^[0-9]\+$' | sort -n | tail -1)

# Ensure minimum RTT isn't negative
min_y=$(( min_rtt < 5 ? 0 : min_rtt - 5 ))
max_y=$(( max_rtt + 5 ))

echo "🔍 Debug: RTT Range = $min_y to $max_y"

# Show RTT List with Bars
# --------------------------
echo -e "\n📊 RTT Values Ordered by Time with Bar Indicator:\n"

max_bar_length=50  # Maximum bar width in characters

awk -v max_rtt="$max_rtt" -v max_bar_length="$max_bar_length" '
{
    scale = (max_rtt > 0) ? $4 / max_rtt : 0;   # Normalize RTT value
    num_blocks = int(scale * max_bar_length);   # Scale to max width
    bar = ""; 
    for (i = 0; i < num_blocks; i++) bar = bar "█";  # Generate bar
    printf "%s | %4d ms | %s\n", $2, $4, bar
}' "$log_filtered.peer" | sort -k1,1


# --------------------------
# 📊 Live RTT Graph with `gnuplot`
# --------------------------

gnuplot -persist <<-EOF
    set title "RTT Over Time for Peer: $selected_peer (Last Hour)"
    set xdata time
    set timefmt "%H:%M:%S"
    set format x "%H:%M"
    set xlabel "Time (HH:MM)"
    set ylabel "RTT (ms)"
    set grid

    # Set X-axis to the last hour with minute-based intervals
    now = system("date +'%H:%M:%S'")
    set xrange [strptime("%H:%M:%S", now)-3600:strptime("%H:%M:%S", now)]
    set xtics 300  # X-axis ticks every 5 minutes

    # Use precomputed Y-axis range
    set yrange [$min_y:$max_y]
    set ytics auto  # Auto-scale Y-axis ticks

    set term dumb 120 30  # Use ASCII graph output
#    set terminal ansi256
    plot "$log_filtered.peer" using 2:4 with linespoints title "RTT (ms)" lc rgb "magenta"

EOF