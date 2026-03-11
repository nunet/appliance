#!/bin/bash
# Plugin: prometheus
# Description: Uninstall Prometheus installed as a systemd service.
# Version: $(cat "$(dirname "$0")/version")

set -e

SERVICE_NAME="prometheus"
SERVICE_TYPE="systemd"
SYSTEMD_SERVICE_FILE="/etc/systemd/system/prometheus.service"
REGISTRY="/etc/appliance/installed_components.conf"
DATA_DIR="/var/lib/prometheus"

prompt_backup() {
    echo "Do you want to back up Prometheus data before uninstalling? (y/n)"
    read -r answer
    case "$answer" in
        y|Y|yes|YES)
            TIMESTAMP=$(date +%Y%m%d_%H%M%S)
            BACKUP_DIR="${DATA_DIR}_backup_${TIMESTAMP}"
            echo "[INFO] Backing up data from ${DATA_DIR} to ${BACKUP_DIR}..."
            sudo cp -r "${DATA_DIR}" "${BACKUP_DIR}"
            echo "[INFO] Backup complete."
            ;;
        *)
            echo "[INFO] Skipping backup."
            ;;
    esac
}

uninstall_service() {
    echo "[INFO] Preparing to uninstall Prometheus..."
    # Prompt for backup
    prompt_backup

    echo "[INFO] Stopping Prometheus service..."
    sudo systemctl stop prometheus
    echo "[INFO] Disabling Prometheus service..."
    sudo systemctl disable prometheus
    echo "[INFO] Removing Prometheus systemd service file..."
    sudo rm -f "${SYSTEMD_SERVICE_FILE}"
    echo "[INFO] Cleaning up registry entry..."
    sudo sed -i "/^${SERVICE_NAME}:/d" "${REGISTRY}"
    echo "[INFO] Prometheus uninstalled."
}

case "$1" in
    uninstall)
        uninstall_service
        ;;
    *)
        echo "Usage: $0 uninstall"
        exit 1
        ;;
esac
