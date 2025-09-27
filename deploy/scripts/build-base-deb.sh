#!/usr/bin/env bash
set -euo pipefail

PKGNAME="nunet-appliance-base"
PKGVERSION="${1:-1.0.0}"
ARCH="${2:-arm64}"

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
  "apm": {
    "api_key": "",
    "environment": "production",
    "server_url": "https://apm.telemetry.nunet.io",
    "service_name": "nunet-dms"
  },
  "general": {
    "env": "production",
    "data_dir": "/home/nunet/nunet/data",
    "debug": false,
    "port_available_range_from": 1024,
    "port_available_range_to": 32768,
    "user_dir": "/home/nunet/.nunet",
    "work_dir": "/home/nunet/nunet"
  },
  "job": {
    "allow_privileged_docker": false
  },
  "observability": {
    "elasticsearch_api_key": "",
    "elasticsearch_enabled": false,
    "elasticsearch_index": "nunet-dms",
    "elasticsearch_url": "http://localhost:9200",
    "flush_interval": 5,
    "insecure_skip_verify": true,
    "log_file": "/home/nunet/logs/nunet-dms.log",
    "log_level": "DEBUG",
    "max_age": 28,
    "max_backups": 3,
    "max_size": 100
  },
  "p2p": {
    "bootstrap_peers": [
      "/dnsaddr/bootstrap.p2p.nunet.io/p2p/12D3KooWHzew9HTYzywFuvTHGK5Yzoz7qAhMfxagtCvhvjheoBQ3",
      "/dnsaddr/bootstrap.p2p.nunet.io/p2p/12D3KooWJMtMN1mTNRfgMqUygT7eSXamVzc9ihpSjeairm9PebmB",
      "/dnsaddr/bootstrap.p2p.nunet.io/p2p/12D3KooWKjSodxxi7UfRHzuk7eGgUF49MoPUCJvtva9K12TqDDsi"
    ],
    "fd": 512,
    "listen_address": [
      "/ip4/0.0.0.0/tcp/9000",
      "/ip4/0.0.0.0/udp/9000/quic-v1"
    ],
    "memory": 1024
  },
  "profiler": {
    "addr": "127.0.0.1",
    "enabled": true,
    "port": 6060
  },
  "rest": {
    "addr": "127.0.0.1",
    "port": 9999
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

# Copy splash screen files
cp backend/scripts/nunet_boot_splash.py "$ROOT/home/ubuntu/nunet/appliance/backend/scripts/"
chmod 0755 "$ROOT/home/ubuntu/nunet/appliance/backend/scripts/nunet_boot_splash.py"

# Note: .bashrc modification will be done in postinst to append to existing file

# --- DEBIAN metadata ---
cat > "$ROOT/DEBIAN/control" <<EOF
Package: nunet-appliance-base
Version: $PKGVERSION
Section: utils
Priority: optional
Architecture: $ARCH
Depends: systemd, snapd
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

# Set ownership for splash files
chown ubuntu:ubuntu /home/ubuntu/nunet/appliance/backend/scripts/nunet_boot_splash.py

# Append splash launcher to existing .bashrc (only if not already present)
if [ -f /home/ubuntu/.bashrc ] && ! grep -q "NuNet Appliance Boot Splash Screen" /home/ubuntu/.bashrc; then
    echo "" >> /home/ubuntu/.bashrc
    echo "# NuNet Appliance Boot Splash Screen" >> /home/ubuntu/.bashrc
    echo "# Show splash screen on login" >> /home/ubuntu/.bashrc
    echo "if [ -f /home/ubuntu/nunet/appliance/backend/scripts/nunet_boot_splash.py ] && [ -t 1 ]; then" >> /home/ubuntu/.bashrc
    echo "    python3 /home/ubuntu/nunet/appliance/backend/scripts/nunet_boot_splash.py 2>/dev/null || true" >> /home/ubuntu/.bashrc
    echo "fi" >> /home/ubuntu/.bashrc
    chown ubuntu:ubuntu /home/ubuntu/.bashrc
fi

# Install snap packages
if [ -f /usr/local/bin/install-snaps.sh ]; then
    /usr/local/bin/install-snaps.sh
fi

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
