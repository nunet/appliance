#!/usr/bin/env bash
set -euo pipefail

PKGNAME="nunet-appliance-base"
PKGVERSION="${1:-1.0.0}"
ARCH="${2:-arm64}"
DEB_VERSION="$(echo "${PKGVERSION}" | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -n1 || true)"
if [ -z "$DEB_VERSION" ]; then
  DEB_VERSION="${PACKAGE_VERSION_FALLBACK:-0.0.0}"
  echo "Warning: invalid package version '${PKGVERSION}', falling back to Debian version '${DEB_VERSION}'."
fi

# Resolve repository root from deploy/scripts
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_REPO="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$ROOT_REPO"

DEST="dist"
ROOT="$DEST/${PKGNAME}_${PKGVERSION}_${ARCH}"

rm -rf "$ROOT"
mkdir -p "$ROOT/DEBIAN"
mkdir -p "$ROOT/usr/local/bin"
mkdir -p "$ROOT/home/nunet/scripts"
mkdir -p "$ROOT/home/nunet/config"
mkdir -p "$ROOT/home/ubuntu/scripts"
mkdir -p "$ROOT/home/ubuntu/nunet/appliance/known_orgs"
mkdir -p "$ROOT/home/ubuntu/nunet/appliance/deployments"
mkdir -p "$ROOT/home/ubuntu/nunet/appliance/backend/scripts"
mkdir -p "$ROOT/etc/systemd/system"
mkdir -p "$ROOT/var/lib/nunet-appliance"

# --- payload ---

# Setup script for nunet users and directories
cat > "$ROOT/usr/local/bin/setup-nunet-users.sh" <<'EOF'
#!/bin/bash
set -e

echo "Setting up NuNet users and directories..."

# Create nunet user if it doesn't exist
if ! id -u nunet >/dev/null 2>&1; then
    useradd -m -d /home/nunet -s /usr/sbin/nologin nunet
    echo "Created nunet user with home /home/nunet."
else
    echo "nunet user already exists."
fi

# Create required directories
for dir in ".nunet/key" ".nunet/cap" "config" "logs" ".secrets" "scripts" "nunet" "nunet/deployments"; do
    mkdir -p /home/nunet/"$dir"
    echo "Created /home/nunet/$dir"
done

# Set permissions (always update to ensure correct ownership)
chown -R nunet:nunet /home/nunet
chmod -R 0770 /home/nunet

# Add ubuntu to nunet group (idempotent)
if ! groups ubuntu | grep -q nunet; then
    usermod -aG nunet ubuntu
    echo "Added ubuntu to the nunet group."
else
    echo "ubuntu already in nunet group."
fi

# Set setgid bit on directories (idempotent)
chmod g+s /home/nunet/.nunet/key
chmod g+s /home/nunet/.nunet/cap
chmod g+s /home/nunet/.secrets
chmod g+s /home/nunet/nunet
chmod g+s /home/nunet/nunet/deployments
# Create ubuntu scripts directory
mkdir -p /home/ubuntu/scripts
chown ubuntu:ubuntu /home/ubuntu/scripts

echo "User setup complete."
EOF
chmod 0755 "$ROOT/usr/local/bin/setup-nunet-users.sh"

# Keyring scripts
cat > "$ROOT/home/nunet/scripts/load-nunet-user-keyring.sh" <<'EOF'
#!/bin/bash
set -e

# Remove any existing key with the same description from the nunet user's keyring
existing_key=$(keyctl search @u user dms_passphrase 2>/dev/null || true)
if [ -n "$existing_key" ]; then
    keyctl unlink "$existing_key" @u
    echo "Removed existing DMS passphrase from keyring."
fi

# Load the DMS passphrase into the keyring
if [ -f /home/nunet/.secrets/dms_passphrase ]; then
    echo "Loading DMS passphrase into keyring..."
    keyctl padd user dms_passphrase @u < /home/nunet/.secrets/dms_passphrase
    echo "DMS passphrase loaded into keyring."
    
    # Delete the secret after we have loaded it into the keyring for security
    # We can expect it to be replaced by the ubuntu user on reboot
    rm /home/nunet/.secrets/dms_passphrase
    echo "Passphrase file deleted for security."
else
    echo "DMS passphrase file not found. Skipping keyring load."
fi
EOF
chmod 0755 "$ROOT/home/nunet/scripts/load-nunet-user-keyring.sh"

cat > "$ROOT/home/ubuntu/scripts/load-ubuntu-user-keyring.sh" <<'EOF'
#!/bin/bash
set -e

# Remove any existing key with the same description from the ubuntu user's keyring
existing_key=$(keyctl search @u user dms_passphrase 2>/dev/null || true)
if [ -n "$existing_key" ]; then
    keyctl unlink "$existing_key" @u
    echo "Removed existing DMS passphrase from keyring."
fi

# Load the DMS passphrase into the keyring
if [ -f /home/ubuntu/.secrets/dms_passphrase ]; then
    echo "Loading DMS passphrase into keyring..."
    keyctl padd user dms_passphrase @u < /home/ubuntu/.secrets/dms_passphrase
    echo "DMS passphrase loaded into keyring."
    
    # Once we have loaded the keyring, copy the secret to the nunet user's secret location
    # Their keyring loader will pick it up then delete it for security, so we need to put it back again on reboot
    sudo cp /home/ubuntu/.secrets/dms_passphrase /home/nunet/.secrets/
    # Fix perms to allow the nunet user to read and delete the file
    sudo chown nunet:nunet /home/nunet/.secrets/dms_passphrase
    echo "Passphrase copied to nunet user location."
else
    echo "DMS passphrase file not found. Skipping keyring load."
fi
EOF
chmod 0755 "$ROOT/home/ubuntu/scripts/load-ubuntu-user-keyring.sh"

# DMS run script
cat > "$ROOT/home/nunet/scripts/rundms.sh" <<'EOF'
#!/bin/bash
set -e

# Retrieve the passphrase securely from the keyring
export DMS_PASSPHRASE=$(keyctl pipe $(keyctl request user dms_passphrase) 2>/dev/null)

if [ -z "$DMS_PASSPHRASE" ]; then
    echo "DMS passphrase not found in keyring. Please run load-nunet-user-keyring.sh first."
    exit 1
fi

# Execute the DMS command with proper config
echo "Starting DMS..."
exec /usr/bin/nunet --config /home/nunet/config/dms_config.json run -c dms
EOF
chmod 0755 "$ROOT/home/nunet/scripts/rundms.sh"

# DMS config
cat > "$ROOT/home/nunet/config/dms_config.json" <<'EOF'
{
    "profiler": {
        "enabled": true,
        "addr": "127.0.0.1",
        "port": 6060
    },
    "general": {
        "env": "production",
        "user_dir": "/home/nunet/.nunet",
        "work_dir": "/home/nunet/nunet",
        "data_dir": "/home/nunet/nunet/data",
        "debug": false,
        "host_city": "",
        "host_country": "",
        "host_continent": "",
        "port_available_range_from": 1024,
        "port_available_range_to": 32768,
        "storage_mode": false,
        "storage_ca_directory": "/home/nunet/.nunet/storage_ca_directory",
        "storage_bricks_dir": "/home/nunet/.nunet/storage_bricks_dir",
        "storage_glusterfs_hostname": "",
        "compute_gateway": false,
        "providers": null,
        "payment_provider": {
            "mode": false,
            "ethereum_rpc_url": "https://ethereum-sepolia-rpc.publicnode.com",
            "ethereum_rpc_token": "",
            "ntx_contract_address": "0xB37216b70a745129966E553cF8Ee2C51e1cB359A",
            "block_frost_api_url": "",
            "block_frost_api_key": "",
            "cardano_asset_name": "",
            "cardano_asset_policy_id": ""
        }
    },
    "rest": {
        "addr": "127.0.0.1",
        "port": 9999
    },
    "p2p": {
        "listen_address": [
            "/ip4/0.0.0.0/tcp/9000",
            "/ip4/0.0.0.0/udp/9000/quic-v1"
        ],
        "bootstrap_peers": [
            "/dnsaddr/bootstrap.p2p.nunet.io/p2p/12D3KooWHzew9HTYzywFuvTHGK5Yzoz7qAhMfxagtCvhvjheoBQ3",
            "/dnsaddr/bootstrap.p2p.nunet.io/p2p/12D3KooWJMtMN1mTNRfgMqUygT7eSXamVzc9ihpSjeairm9PebmB",
            "/dnsaddr/bootstrap.p2p.nunet.io/p2p/12D3KooWKjSodxxi7UfRHzuk7eGgUF49MoPUCJvtva9K12TqDDsi"
        ],
        "memory": 1024,
        "fd": 512
    },
    "job": {
        "allow_privileged_docker": false,
        "require_contracts_for_deployment": true
    },
    "observability": {
        "logging": {
            "level": "DEBUG",
            "file": "/home/nunet/logs/nunet-dms.log",
            "rotation": {
                "max_size_mb": 100,
                "max_backups": 3,
                "max_age_days": 28
            }
        },
        "elastic": {
            "url": "https://telemetry.nunet.io",
            "index": "nunet-dms",
            "flush_interval": 5,
            "enabled": false,
            "api_key": "",
            "insecure_skip_verify": true
        },
        "otel": {
            "enabled": true,
            "endpoint": "otel.nunet.network:4317",
            "insecure": true
        }
    },
    "apm": {
        "server_url": "https://apm.telemetry.nunet.io",
        "service_name": "nunet-dms",
        "environment": "production",
        "api_key": "",
        "secret_token": ""
    },
    "coinmarketcap": {
        "api_key": "",
        "base_url": "",
        "endpoint_path": "",
        "cache_ttl": "",
        "quote_ttl": ""
    }
}
EOF


# Systemd services
cat > "$ROOT/etc/systemd/system/loadubuntukeyring.service" <<'EOF'
[Unit]
Description=Load DMS Passphrase into Kernel Keyring for ubuntu
After=network.target
Before=loadnunetkeyring.service

[Service]
Type=oneshot
User=ubuntu
Group=ubuntu
ExecStart=/home/ubuntu/scripts/load-ubuntu-user-keyring.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

cat > "$ROOT/etc/systemd/system/loadnunetkeyring.service" <<'EOF'
[Unit]
Description=Load DMS Passphrase into Kernel Keyring for nunet
After=loadubuntukeyring.service
Before=nunetdms.service

[Service]
Type=oneshot
User=nunet
Group=nunet
ExecStart=/home/nunet/scripts/load-nunet-user-keyring.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

# DMS service
cat > "$ROOT/etc/systemd/system/nunetdms.service" <<'EOF'
[Unit]
Description=NuNet Device Management Service
After=network.target docker.service loadnunetkeyring.service loadubuntukeyring.service
Requires=docker.service loadnunetkeyring.service loadubuntukeyring.service

[Service]
User=nunet
Group=nunet
KeyringMode=shared
Environment=GOLOG_LOG_LEVEL=debug
ExecStart=/home/nunet/scripts/rundms.sh
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Snap installation script
cat > "$ROOT/usr/local/bin/install-snaps.sh" <<'EOF'
#!/bin/bash
set -e

echo "Installing snap packages..."

# Install wormhole snap
if ! snap list wormhole >/dev/null 2>&1; then
    snap install wormhole
    echo "Installed wormhole snap."
else
    echo "wormhole snap already installed."
fi

echo "Snap installation complete."
EOF
chmod 0755 "$ROOT/usr/local/bin/install-snaps.sh"

# Note: Splash screen is now installed by nunet-appliance-web package

# --- DEBIAN metadata ---
cat > "$ROOT/DEBIAN/control" <<EOF
Package: nunet-appliance-base
Version: $DEB_VERSION
Section: utils
Priority: optional
Architecture: $ARCH
Depends: systemd, snapd, avahi-daemon
Maintainer: NuNet <ops@nunet.io>
Description: NuNet Appliance Base System
 Base system setup for NuNet appliances including:
 - User and directory setup
 - Keyring management
 - DMS service configuration
 - Snap package installation
 - Systemd service configuration
EOF

# post-install: setup users, install snaps, reload systemd
cat > "$ROOT/DEBIAN/postinst" <<'EOF'
#!/bin/sh -e

# Wait a moment for files to be fully extracted
sleep 1

# Setup users and directories
if [ -f /usr/local/bin/setup-nunet-users.sh ]; then
    /usr/local/bin/setup-nunet-users.sh
fi

# Create appliance directory structure
mkdir -p /home/ubuntu/nunet/appliance/known_orgs
mkdir -p /home/ubuntu/nunet/appliance/deployments
mkdir -p /home/ubuntu/nunet/appliance/backend/scripts
chown ubuntu:ubuntu /home/ubuntu/nunet/appliance
chown ubuntu:ubuntu /home/ubuntu/nunet/appliance/known_orgs
chown ubuntu:ubuntu /home/ubuntu/nunet/appliance/deployments
chown ubuntu:ubuntu /home/ubuntu/nunet/appliance/backend/scripts
chmod 755 /home/ubuntu/nunet/appliance
chmod 755 /home/ubuntu/nunet/appliance/known_orgs
chmod 755 /home/ubuntu/nunet/appliance/deployments
chmod 755 /home/ubuntu/nunet/appliance/backend/scripts

# Set correct permission on DMS config
chmod 0660 /home/nunet/config/dms_config.json
chown nunet:nunet /home/nunet/config/dms_config.json

# Note: Splash screen installation and .bashrc modification are now handled by nunet-appliance-web package

# Install snap packages
if [ -f /usr/local/bin/install-snaps.sh ]; then
    /usr/local/bin/install-snaps.sh
fi

# --- Derive and set unique hostname (nunet-<6hex>) ---
derive_suffix() {
    if [ -f /etc/machine-id ]; then
        head -c 6 /etc/machine-id | tr '[:upper:]' '[:lower:]'
        return 0
    fi
    # fallback: MAC suffix
    ip link show | awk '/link\/ether/ {print $2}' | head -n1 | tr -d ':' | tail -c 6
}

current_host="$(hostnamectl --static 2>/dev/null || hostname)"
# Check if hostname already matches nunet-<6hex> pattern
if echo "$current_host" | grep -qE '^nunet-[0-9a-f]{6}$'; then
    # Already has unique format, keep it
    echo "Hostname already in unique format: $current_host"
else
    # Set to unique format
    suf="$(derive_suffix)"
    if [ -n "$suf" ]; then
        new_host="nunet-${suf}"
        hostnamectl set-hostname "$new_host" || true
        echo "Set hostname to unique format: $new_host"
    fi
fi

# --- Configure Avahi (mDNS) to advertise HTTPS on 8443 ---
systemctl enable avahi-daemon.service >/dev/null 2>&1 || true
systemctl start avahi-daemon.service || true

AVAHI_SVC_DIR="/etc/avahi/services"
mkdir -p "$AVAHI_SVC_DIR"
AVAHI_SVC_FILE="$AVAHI_SVC_DIR/nunet-appliance-https.service"
HOSTNAME_NOW="$(hostnamectl --static 2>/dev/null || hostname)"
cat > "$AVAHI_SVC_FILE" <<AVEOF
<?xml version="1.0" standalone='no'?><!--*-nxml-*-->
<!DOCTYPE service-group SYSTEM "avahi-service.dtd">
<service-group>
  <name replace-wildcards="yes">NuNet Appliance Web on %h</name>
  <service>
    <type>_https._tcp</type>
    <port>8443</port>
    <txt-record>path=/</txt-record>
    <txt-record>hostname=${HOSTNAME_NOW}.local</txt-record>
  </service>
</service-group>
AVEOF

systemctl restart avahi-daemon.service || true

# Reload systemd
systemctl daemon-reload

# Enable keyring services
systemctl enable loadubuntukeyring.service >/dev/null 2>&1 || true
systemctl enable loadnunetkeyring.service >/dev/null 2>&1 || true
systemctl start loadubuntukeyring.service || true
systemctl start loadnunetkeyring.service || true

# Enable DMS service
systemctl enable nunetdms.service >/dev/null 2>&1 || true

exit 0
EOF
chmod 0755 "$ROOT/DEBIAN/postinst"

# pre-remove: stop and disable services
cat > "$ROOT/DEBIAN/prerm" <<'EOF'
#!/bin/sh -e
systemctl stop nunetdms.service || true
systemctl disable nunetdms.service || true
systemctl stop loadnunetkeyring.service || true
systemctl disable loadnunetkeyring.service || true
systemctl stop loadubuntukeyring.service || true
systemctl disable loadubuntukeyring.service || true
exit 0
EOF
chmod 0755 "$ROOT/DEBIAN/prerm"

# post-remove: clean up
cat > "$ROOT/DEBIAN/postrm" <<'EOF'
#!/bin/sh -e
rm -f /etc/systemd/system/nunetdms.service || true
rm -f /etc/systemd/system/loadnunetkeyring.service || true
rm -f /etc/systemd/system/loadubuntukeyring.service || true
systemctl daemon-reload || true
exit 0
EOF
chmod 0755 "$ROOT/DEBIAN/postrm"

# --- build the deb ---
mkdir -p "$DEST"
fakeroot dpkg-deb --build "$ROOT" "$DEST/${PKGNAME}_${PKGVERSION}_${ARCH}.deb"

echo "Built: $DEST/${PKGNAME}_${PKGVERSION}_${ARCH}.deb"
