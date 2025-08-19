#!/usr/bin/env bash

###############################################################################
# 1) CPU: total cores minus 1
###############################################################################
CPU_CORES=$(nproc)
CPU_ONBOARD=$(( CPU_CORES - 1 ))
# Optionally ensure it never goes below 1:
if [ "$CPU_ONBOARD" -lt 1 ]; then
  CPU_ONBOARD=1
fi

###############################################################################
# 2) RAM in GiB
#    - Total from /proc/meminfo (KiB) -> GiB
#    - Used from "free -k" (KiB) -> GiB
#    - Free = (Total - Used)
#    - Floor free RAM to nearest 0.5 GiB
#    - Onboard RAM = min(floored free RAM, 89% of total)
###############################################################################
# Total RAM in KiB
TOTAL_RAM_KB=$(awk '/MemTotal:/ {print $2}' /proc/meminfo)
# Convert KiB -> GiB
TOTAL_RAM_GB=$(awk -v kb="$TOTAL_RAM_KB" 'BEGIN {printf "%.2f", kb / 1048576}')

# Current used RAM from "free -k"
CURRENT_RAM_USED_KB=$(free -k | awk '/Mem:/ {print $3}')
CURRENT_RAM_USED_GB=$(awk -v kb="$CURRENT_RAM_USED_KB" 'BEGIN {printf "%.2f", kb / 1048576}')

# Current percentage utilization
RAM_UTIL_PERCENT=$(awk -v used="$CURRENT_RAM_USED_KB" -v total="$TOTAL_RAM_KB" \
  'BEGIN {printf "%.2f", (used / total) * 100}')

# Free RAM in GiB
FREE_RAM_GB=$(awk -v t="$TOTAL_RAM_GB" -v u="$CURRENT_RAM_USED_GB" \
  'BEGIN {printf "%.2f", t - u}')

# Floor free RAM to the nearest 0.5 GiB
FLOORED_FREE_RAM_GB=$(awk -v f="$FREE_RAM_GB" 'BEGIN {
  if (f < 0) { f = 0 }
  x = int(f * 2) / 2
  printf "%.1f", x
}')

# 89% of total RAM
RAM_89_PERCENT_GB=$(awk -v t="$TOTAL_RAM_GB" 'BEGIN {printf "%.1f", t * 0.89}')

# Choose the smaller value between floored free RAM and 89% of total
RAM_ONBOARD_GB=$(awk -v f="$FLOORED_FREE_RAM_GB" -v p="$RAM_89_PERCENT_GB" \
  'BEGIN {printf "%.1f", (f < p) ? f : p}')

###############################################################################
# 3) Disk in GiB
#    - Use df -k --total to get free space in KiB
#    - Convert KiB -> GiB
#    - Subtract 5 GiB
###############################################################################
FREE_DISK_KB=$(df -k --total | tail -1 | awk '{print $4}')
FREE_DISK_GB=$(awk -v kb="$FREE_DISK_KB" 'BEGIN {printf "%.2f", kb / 1048576}')

# Subtract 5 GiB
DISK_ONBOARD_GB=$(awk -v free_gb="$FREE_DISK_GB" 'BEGIN {
  x = free_gb - 5
  if (x < 0) x=0
  printf "%.2f", x
}')

###############################################################################
# Display results
###############################################################################
echo "===== Raw System Resources ====="
echo "Total CPU cores:            $CPU_CORES"
echo "Total RAM (GiB):            $TOTAL_RAM_GB"
echo "Free Disk (GiB):            $FREE_DISK_GB"

echo
echo "===== Current RAM Utilization ====="
echo "Used RAM (GiB):             $CURRENT_RAM_USED_GB"
echo "RAM Utilization (%):        $RAM_UTIL_PERCENT%"

echo
echo "===== Onboard Resources (Calculated) ====="
echo "CPU cores to onboard:       $CPU_ONBOARD"
echo "RAM to onboard (GiB):       $RAM_ONBOARD_GB"
echo "Disk to onboard (GiB):      $DISK_ONBOARD_GB"

echo 
echo "===== Onbarding DMS ====="
nunet -c dms actor cmd /dms/node/onboarding/onboard --disk $DISK_ONBOARD_GB --ram $RAM_ONBOARD_GB --cpu $CPU_ONBOARD



