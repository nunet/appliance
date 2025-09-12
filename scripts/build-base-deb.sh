#!/usr/bin/env bash
set -euo pipefail

PKGNAME="nunet-appliance-base"
PKGVERSION="${1:-1.0.0}"
ARCH="${2:-arm64}"

cd "$(dirname "$0")/.."

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
for dir in ".nunet/key" ".nunet/cap" "config" "logs" ".secrets" "scripts" "nunet"; do
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

# Load the DMS passphrase into the keyring
if [ -f /home/nunet/.secrets/dms_passphrase ]; then
    echo "Loading DMS passphrase into keyring..."
    keyctl add user dms_passphrase "$(cat /home/nunet/.secrets/dms_passphrase)" @u
    echo "DMS passphrase loaded into keyring."
else
    echo "DMS passphrase file not found. Skipping keyring load."
fi
EOF
chmod 0755 "$ROOT/home/nunet/scripts/load-nunet-user-keyring.sh"

cat > "$ROOT/home/ubuntu/scripts/load-ubuntu-user-keyring.sh" <<'EOF'
#!/bin/bash
set -e

# Load the DMS passphrase into the keyring
if [ -f /home/nunet/.secrets/dms_passphrase ]; then
    echo "Loading DMS passphrase into keyring..."
    keyctl add user dms_passphrase "$(cat /home/nunet/.secrets/dms_passphrase)" @u
    echo "DMS passphrase loaded into keyring."
else
    echo "DMS passphrase file not found. Skipping keyring load."
fi
EOF
chmod 0755 "$ROOT/home/ubuntu/scripts/load-ubuntu-user-keyring.sh"

# DMS run script
cat > "$ROOT/home/nunet/scripts/rundms.sh" <<'EOF'
#!/bin/bash
set -e

# Get passphrase from keyring
PASSPHRASE=$(keyctl print @u 2>/dev/null | grep dms_passphrase | cut -d: -f2 | tr -d ' ')

if [ -z "$PASSPHRASE" ]; then
    echo "DMS passphrase not found in keyring. Please run load-nunet-user-keyring.sh first."
    exit 1
fi

# Run DMS with the passphrase
echo "Starting DMS..."
export DMS_PASSPHRASE="$PASSPHRASE"
exec /usr/local/bin/dms
EOF
chmod 0755 "$ROOT/home/nunet/scripts/rundms.sh"

# DMS config
cat > "$ROOT/home/nunet/config/dms_config.json" <<'EOF'
{
  "dms": {
    "passphrase_file": "/home/nunet/.secrets/dms_passphrase",
    "data_dir": "/home/nunet/nunet",
    "log_level": "info"
  }
}
EOF

# Systemd services
cat > "$ROOT/etc/systemd/system/loadubuntukeyring.service" <<'EOF'
[Unit]
Description=Load Ubuntu User Keyring
After=multi-user.target

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
Description=Load NuNet User Keyring
After=multi-user.target

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
Description=NuNet DMS Service
After=network.target loadnunetkeyring.service
Wants=loadnunetkeyring.service

[Service]
Type=simple
User=nunet
Group=nunet
WorkingDirectory=/home/nunet
ExecStart=/home/nunet/scripts/rundms.sh
Restart=on-failure
RestartSec=5
Environment=DMS_PASSPHRASE_FILE=/home/nunet/.secrets/dms_passphrase

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
chown ubuntu:ubuntu /home/ubuntu/nunet/appliance
chown ubuntu:ubuntu /home/ubuntu/nunet/appliance/known_orgs
chown ubuntu:ubuntu /home/ubuntu/nunet/appliance/deployments
chmod 755 /home/ubuntu/nunet/appliance
chmod 755 /home/ubuntu/nunet/appliance/known_orgs
chmod 755 /home/ubuntu/nunet/appliance/deployments

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
