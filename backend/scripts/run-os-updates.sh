#!/bin/bash
set -e

echo "[INFO] Updating package lists..."
for i in {1..3}; do
    apt-get update && break || sleep 5
done

echo "[INFO] Performing full upgrade..."
apt-get -y dist-upgrade

echo "[INFO] Cleaning up unused packages..."
apt-get -y autoremove --purge
apt-get clean

echo "[INFO] System update completed."
