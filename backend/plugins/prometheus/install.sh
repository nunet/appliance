#!/bin/bash
# Plugin: prometheus
# Description: Install Prometheus as a systemd service on Linux with architecture detection.
# Version: $(cat "$(dirname "$0")/version")

set -e

SERVICE_NAME="prometheus"
SERVICE_TYPE="systemd"
SYSTEMD_SERVICE_FILE="/etc/systemd/system/prometheus.service"
REGISTRY="/etc/appliance/installed_components.conf"
PROMETHEUS_VERSION=$(cat "$(dirname "$0")/version")

# Detect architecture
ARCH=$(uname -m)
echo "[INFO] Detected architecture: ${ARCH}"
case "${ARCH}" in
    x86_64|amd64)
        PLATFORM="linux-amd64"
        ;;
    aarch64|arm64)
        PLATFORM="linux-arm64"
        ;;
    *)
        echo "[ERROR] Unsupported architecture: ${ARCH}"
        exit 1
        ;;
esac

download_and_extract() {
    local tarball="prometheus-${PROMETHEUS_VERSION}.${PLATFORM}.tar.gz"
    echo "[INFO] Downloading ${tarball}..."
    cd /tmp
    if command -v wget >/dev/null 2>&1; then
        wget "https://github.com/prometheus/prometheus/releases/download/v${PROMETHEUS_VERSION}/${tarball}"
    else
        curl -LO "https://github.com/prometheus/prometheus/releases/download/v${PROMETHEUS_VERSION}/${tarball}"
    fi
    tar xzf "${tarball}"
}

install_service() {
    echo "[INFO] Installing Prometheus version ${PROMETHEUS_VERSION}..."
    download_and_extract
    local extracted_dir="prometheus-${PROMETHEUS_VERSION}.${PLATFORM}"
    sudo mv "${extracted_dir}/prometheus" /usr/local/bin/
    sudo mv "${extracted_dir}/promtool" /usr/local/bin/
    sudo mkdir -p /etc/prometheus /var/lib/prometheus
    sudo mv "${extracted_dir}/consoles" /etc/prometheus/
    sudo mv "${extracted_dir}/console_libraries" /etc/prometheus/
    sudo useradd --no-create-home --shell /bin/false prometheus 2>/dev/null || true
    sudo chown -R prometheus:prometheus /etc/prometheus /var/lib/prometheus

    cat <<EOF | sudo tee ${SYSTEMD_SERVICE_FILE}
[Unit]
Description=Prometheus
After=network.target

[Service]
User=prometheus
ExecStart=/usr/local/bin/prometheus --config.file=/etc/prometheus/prometheus.yml --storage.tsdb.path=/var/lib/prometheus --web.listen-address=":9090"

[Install]
WantedBy=default.target
EOF

    sudo systemctl daemon-reload
    sudo systemctl enable --now prometheus

    # Register in central registry
    echo "${SERVICE_NAME}:${SERVICE_TYPE}:${SYSTEMD_SERVICE_FILE}:v${PROMETHEUS_VERSION}" | sudo tee -a ${REGISTRY}
    echo "[INFO] Prometheus installation complete."
}

uninstall_service() {
    echo "[INFO] Uninstalling Prometheus..."
    sudo systemctl stop prometheus
    sudo systemctl disable prometheus
    sudo rm -f ${SYSTEMD_SERVICE_FILE}
    sudo sed -i "/^${SERVICE_NAME}:/d" ${REGISTRY}
    echo "[INFO] Prometheus uninstalled."
}

case "$1" in
    install)
        install_service
        ;;
    uninstall)
        uninstall_service
        ;;
    *)
        echo "Usage: $0 {install|uninstall}"
        exit 1
        ;;
esac
