#!/usr/bin/env bash
set -euo pipefail

# -------- settings you may tweak ----------
VERSION="${1:-1.0.0}"                 # deb version; pass as 1st arg to override
DEB_VERSION=$(echo "${VERSION}" | grep -oE '[0-9]+\.[0-9]+\.[0-9]+')
SERVICE_USER="${SERVICE_USER:-ubuntu}" # run the service as this user
# ------------------------------------------

# Resolve repository root from deploy/scripts
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$ROOT"
ARCH="${2:-$(dpkg --print-architecture)}"

echo "==> Building nunet-appliance-web ${VERSION} for ${ARCH} (user: ${SERVICE_USER})"

# --- prerequisites (venv only; no system pip writes) ---
if ! python3 -c 'import venv' 2>/dev/null; then
  echo "Installing python3-venv ..."
  sudo apt-get update
  sudo apt-get install -y python3-venv
fi

# --- ensure frontend build exists ---
if [ ! -f "$ROOT/frontend/dist/index.html" ]; then
  echo "ERROR: frontend/dist not found. Run 'pnpm run build' in ./frontend first."
  exit 1
fi

# --- generate version file for backend (required for PEX build) ---
APPLIANCE_VERSION=$(git describe --tags --always --abbrev=0 --dirty 2>/dev/null | sed 's/^v//' || echo "${VERSION}")
PKGVERSION="${APPLIANCE_VERSION:-${VERSION}}"
echo "__version__ = \"${PKGVERSION}\"" > "$ROOT/backend/_version.py"

# --- build backend: wheels + PEX ---
VENV="$ROOT/.build-venv"
python3 -m venv "$VENV"
# shellcheck disable=SC1090
source "$VENV/bin/activate"
export PIP_DEFAULT_TIMEOUT="${PIP_DEFAULT_TIMEOUT:-120}"
export PIP_RETRIES="${PIP_RETRIES:-5}"
python -m pip install --no-cache-dir --progress-bar off --upgrade pip wheel pex

mkdir -p "$ROOT/release/wheels" "$ROOT/release/frontend-dist"
python -m pip wheel --no-cache-dir --progress-bar off -r "$ROOT/backend/nunet_api/requirements.txt" -w "$ROOT/release/wheels"

(
  cd "$ROOT/backend"
  pex -f "$ROOT/release/wheels" \
      -r nunet_api/requirements.txt \
      -D . \
      -c gunicorn \
      -o "$ROOT/release/nunet-dms.pex"
)

cp -f "$ROOT/deploy/gunicorn_conf.py" "$ROOT/release/gunicorn_conf.py"
cp -a "$ROOT/frontend/dist/." "$ROOT/release/frontend-dist/"

deactivate
rm -rf "$VENV"

# --- build package tree ---
PKGDIR="$ROOT/build/nunet-appliance-web_${VERSION}_${ARCH}"
rm -rf "$PKGDIR"
mkdir -p "$PKGDIR/DEBIAN"
mkdir -p "$PKGDIR/usr/lib/nunet-appliance-web"
mkdir -p "$PKGDIR/usr/share/nunet-appliance-web/frontend/dist"
mkdir -p "$PKGDIR/usr/share/nunet-appliance-web/data/ensembles"
mkdir -p "$PKGDIR/usr/share/nunet-appliance-web/data/contracts"
mkdir -p "$PKGDIR/lib/systemd/system"
mkdir -p "$PKGDIR/etc/systemd/system"
mkdir -p "$PKGDIR/etc/nunet-appliance-web"
mkdir -p "$PKGDIR/home/ubuntu/nunet/appliance/backend/scripts"

# payload
install -m 0755 "$ROOT/release/nunet-dms.pex" "$PKGDIR/usr/lib/nunet-appliance-web/nunet-dms.pex"
install -m 0644 "$ROOT/release/gunicorn_conf.py" "$PKGDIR/usr/lib/nunet-appliance-web/gunicorn_conf.py"
install -m 0755 "$ROOT/deploy/scripts/updater.sh" "$PKGDIR/usr/lib/nunet-appliance-web/updater.sh"
install -m 0755 "$ROOT/deploy/scripts/dms-updater.sh" "$PKGDIR/usr/lib/nunet-appliance-web/dms-updater.sh"
cp -a "$ROOT/release/frontend-dist/." "$PKGDIR/usr/share/nunet-appliance-web/frontend/dist/"

# Include known organizations metadata for backend defaults.
if [ -d "$ROOT/known_orgs" ]; then
  mkdir -p "$PKGDIR/usr/lib/nunet-appliance-web/known_orgs"
  cp -a "$ROOT/known_orgs/." "$PKGDIR/usr/lib/nunet-appliance-web/known_orgs/" || true
fi

# Include default ensembles (if present in repo)
if [ -d "$ROOT/backend/ensembles" ]; then
  cp -a "$ROOT/backend/ensembles/." "$PKGDIR/usr/share/nunet-appliance-web/data/ensembles/" || true
fi


# Include default contracts (if present in repo)
if [ -d "$ROOT/backend/contracts" ]; then
  cp -a "$ROOT/backend/contracts/." "$PKGDIR/usr/share/nunet-appliance-web/data/contracts/" || true
fi

# Copy splash screen script
cp "$ROOT/backend/scripts/nunet_boot_splash.py" "$PKGDIR/home/ubuntu/nunet/appliance/backend/scripts/"
chmod 0755 "$PKGDIR/home/ubuntu/nunet/appliance/backend/scripts/nunet_boot_splash.py"

# default env overrides (editable after install)
cat > "$PKGDIR/etc/nunet-appliance-web/app.env" <<'EOF'
# Overrides for nunet-appliance-web.service (uncomment to change)
#PORT=8080
#WORKERS=1
#NUNET_STATIC_DIR=/usr/share/nunet-appliance-web/frontend/dist
#NUNET_DATA_DIR=/usr/share/nunet-appliance-web/data
EOF

# systemd unit (runs as 'ubuntu' by default)
cat > "$PKGDIR/lib/systemd/system/nunet-appliance-web.service" <<EOF
[Unit]
Description=NuNet Appliance Web (FastAPI + React via Gunicorn)
After=network-online.target
Wants=network-online.target

[Service]
User=${SERVICE_USER}
KeyringMode=shared
WorkingDirectory=/usr/lib/nunet-appliance-web
Environment=PORT=8443
Environment=WORKERS=1
Environment=NUNET_STATIC_DIR=/usr/share/nunet-appliance-web/frontend/dist
Environment=APPLIANCE_ROOT=/home/ubuntu/nunet/appliance
Environment=NUNET_DATA_DIR=/home/ubuntu/nunet
Environment=ENSEMBLES_DIR=/home/ubuntu/ensembles
Environment=CONTRACTS_DIR=/home/ubuntu/contracts
Environment=DMS_CAP_FILE=/home/ubuntu/.nunet/cap/dms.cap
Environment=SERVICE_DMS_CAP_FILE=/home/nunet/.nunet/cap/dms.cap
Environment=NUNET_CONFIG_PATH=/home/nunet/config/dms_config.json
Environment=SSL_CERTFILE=/etc/nunet-appliance-web/ssl/cert.pem
Environment=SSL_KEYFILE=/etc/nunet-appliance-web/ssl/key.pem
Environment=PEX_ROOT=/home/ubuntu/.local/share/nunet-appliance-web/pex
EnvironmentFile=-/etc/nunet-appliance-web/app.env
ExecStart=/usr/bin/python3 /usr/lib/nunet-appliance-web/nunet-dms.pex \\
          -k uvicorn.workers.UvicornWorker \\
          -c /usr/lib/nunet-appliance-web/gunicorn_conf.py \\
          nunet_api.main:app
Restart=on-failure
RestartSec=3

# Hardening (tuned for non-root user). Allow writes to log and data directories.
# NoNewPrivileges=true  # Disabled to allow sudo usage
PrivateTmp=true
PrivateDevices=true
ProtectSystem=full
ProtectHome=read-only
LockPersonality=true
RestrictSUIDSGID=true
SystemCallArchitectures=native
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
UMask=0027
# Allow writes to specific directories
ReadWritePaths=/home/ubuntu/nunet/appliance /home/ubuntu/.cache /home/ubuntu/.local/share/nunet-appliance-web /home/ubuntu/.secrets /home/ubuntu/.nunet/cap /home/nunet/.nunet/cap /home/nunet/config /etc/systemd/system /home/ubuntu/ensembles /home/ubuntu/contracts

[Install]
WantedBy=multi-user.target
EOF

# Caddy proxy monitor service (installed to /etc/systemd/system/)
# Create a wrapper script to run the module from the PEX
# PEX files are zipfiles that can be added to sys.path directly
cat > "$PKGDIR/usr/lib/nunet-appliance-web/run-caddy-proxy-monitor.sh" <<'EOF'
#!/bin/bash
# Wrapper script to run caddy_proxy_manager module from PEX
# Extract interval from first argument or use default
INTERVAL="${1:-30}"

# Use Python to import from the PEX file (PEX files are zipfiles)
exec /usr/bin/python3 -c "
import sys
import os

# Add PEX file to Python path (PEX files are zipfiles containing modules)
pex_path = '/usr/lib/nunet-appliance-web/nunet-dms.pex'
if os.path.exists(pex_path):
    sys.path.insert(0, pex_path)
    
    # Import and run the module
    from modules.caddy_proxy_manager import CaddyProxyManager
    CaddyProxyManager.systemd_monitor_entry(interval=int('${INTERVAL}'))
else:
    raise FileNotFoundError(f'PEX file not found: {pex_path}')
"
EOF
chmod 0755 "$PKGDIR/usr/lib/nunet-appliance-web/run-caddy-proxy-monitor.sh"

cat > "$PKGDIR/etc/systemd/system/nunet-caddy-proxy-monitor.service" <<EOF
[Unit]
Description=NuNet Caddy Proxy Manager Monitor
After=docker.service
Requires=docker.service

[Service]
Type=simple
Restart=always
User=${SERVICE_USER}
WorkingDirectory=/usr/lib/nunet-appliance-web
ExecStart=/usr/lib/nunet-appliance-web/run-caddy-proxy-monitor.sh 30
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

# systemd unit for updater service
cat > "$PKGDIR/lib/systemd/system/nunet-appliance-updater.service" <<EOF
[Unit]
Description=NuNet Appliance Updater
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/lib/nunet-appliance-web/updater.sh
User=root
EOF

# systemd timer for updater
cat > "$PKGDIR/lib/systemd/system/nunet-appliance-updater.timer" <<EOF
[Unit]
Description=Run NuNet Appliance Updater Daily

[Timer]
OnCalendar=daily
Persistent=true

[Install]
WantedBy=timers.target
EOF

# systemd unit for DMS updater service
cat > "$PKGDIR/lib/systemd/system/nunet-dms-updater.service" <<EOF
[Unit]
Description=NuNet DMS Updater
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/lib/nunet-appliance-web/dms-updater.sh
User=root
EOF

# DEBIAN metadata
cat > "$PKGDIR/DEBIAN/control" <<EOF
Package: nunet-appliance-web
Version: ${DEB_VERSION}
Section: web
Priority: optional
Architecture: ${ARCH}
Depends: python3 (>= 3.10), systemd, openssl, iproute2, libminiupnpc-dev, wget
Maintainer: NuNet <maintainer@example.com>
Description: NuNet Appliance Web — FastAPI + React served by Gunicorn/Uvicorn
 Prebuilt PEX + static assets. Installs a systemd service 'nunet-appliance-web'.
EOF

cat > "$PKGDIR/DEBIAN/postinst" <<'EOF'
#!/bin/sh -e
# Create appliance directory with proper permissions
mkdir -p /home/ubuntu/nunet/appliance/known_orgs
mkdir -p /home/ubuntu/nunet/appliance/deployments
# Refresh known organizations defaults from packaged data
if [ -f /usr/lib/nunet-appliance-web/known_orgs/known_organizations.json ]; then
  backup_target="/home/ubuntu/nunet/appliance/known_orgs/known_organizations.json"
  if [ -f "$backup_target" ]; then
    cp "$backup_target" "${backup_target}.bak" || true
  fi
  install -m 0644 -T /usr/lib/nunet-appliance-web/known_orgs/known_organizations.json "$backup_target"
  chown ubuntu:ubuntu "$backup_target" || true
fi
if [ -f /usr/lib/nunet-appliance-web/known_orgs/known_organizations.e2e.json ]; then
  e2e_target="/home/ubuntu/nunet/appliance/known_orgs/known_organizations.e2e.json"
  install -m 0644 -T /usr/lib/nunet-appliance-web/known_orgs/known_organizations.e2e.json "$e2e_target"
  chown ubuntu:ubuntu "$e2e_target" || true
fi
# Create ensembles directory and populate defaults if missing/empty
mkdir -p /home/ubuntu/ensembles
if [ -z "$(ls -A /home/ubuntu/ensembles 2>/dev/null)" ]; then
  if [ -d /usr/share/nunet-appliance-web/data/ensembles ]; then
    cp -a /usr/share/nunet-appliance-web/data/ensembles/. /home/ubuntu/ensembles/
  fi
fi
if [ -d /usr/share/nunet-appliance-web/data/ensembles ]; then
  for tmpl in default-ensemble.json default-contract.json; do
    src="/usr/share/nunet-appliance-web/data/ensembles/${tmpl}"
    dest="/home/ubuntu/ensembles/${tmpl}"
    if [ -f "$src" ] && [ ! -f "$dest" ]; then
      install -m 0644 -T "$src" "$dest"
      chown ubuntu:ubuntu "$dest" || true
    fi
  done
fi

mkdir -p /home/ubuntu/contracts
if [ -z "$(ls -A /home/ubuntu/contracts 2>/dev/null)" ]; then
  if [ -d /usr/share/nunet-appliance-web/data/contracts ]; then
    cp -a /usr/share/nunet-appliance-web/data/contracts/. /home/ubuntu/contracts/
  fi
fi
if [ -d /usr/share/nunet-appliance-web/data/contracts ]; then
  for tmpl in default-contract.json; do
    src="/usr/share/nunet-appliance-web/data/contracts/${tmpl}"
    dest="/home/ubuntu/contracts/${tmpl}"
    if [ -f "$src" ] && [ ! -f "$dest" ]; then
      install -m 0644 -T "$src" "$dest"
      chown ubuntu:ubuntu "$dest" || true
    fi
  done
fi

chown ubuntu:ubuntu /home/ubuntu/nunet/appliance
chown ubuntu:ubuntu /home/ubuntu/nunet/appliance/known_orgs
chown ubuntu:ubuntu /home/ubuntu/nunet/appliance/deployments
chown -R ubuntu:ubuntu /home/ubuntu/ensembles || true
chown -R ubuntu:ubuntu /home/ubuntu/contracts || true


chmod 755 /home/ubuntu/nunet/appliance
chmod 755 /home/ubuntu/nunet/appliance/known_orgs
chmod 755 /home/ubuntu/nunet/appliance/deployments
chmod 755 /home/ubuntu/ensembles || true
chmod 755 /home/ubuntu/contracts || true

# --- Create local volumes directories for ensembles ---
# These directories are used by example ensemble deployments for persistent data storage.
# Each ensemble that requires local volume mounts should have its data directory
# created here to ensure proper permissions and existence before deployment.
LOCAL_VOLUMES_DIR="/home/ubuntu/local_volumes"
mkdir -p "$LOCAL_VOLUMES_DIR/n8n_data"
mkdir -p "$LOCAL_VOLUMES_DIR/ollama"
chown -R ubuntu:ubuntu "$LOCAL_VOLUMES_DIR" || true
chmod 755 "$LOCAL_VOLUMES_DIR" || true
chmod 755 "$LOCAL_VOLUMES_DIR/n8n_data" || true
chmod 755 "$LOCAL_VOLUMES_DIR/ollama" || true

# --- Create .secrets directory and migrate credentials ---
SECRETS_DIR="/home/ubuntu/.secrets"
mkdir -p "$SECRETS_DIR"
chown ubuntu:ubuntu "$SECRETS_DIR" || true
chmod 0700 "$SECRETS_DIR" || true

# Migrate credentials from old PEX cache location if they exist
OLD_CREDS="/home/ubuntu/.cache/pex/user_code/0/deploy/admin_credentials.json"
NEW_CREDS="$SECRETS_DIR/admin_credentials.json"
if [ -f "$OLD_CREDS" ] && [ ! -f "$NEW_CREDS" ]; then
  cp "$OLD_CREDS" "$NEW_CREDS" || true
  chown ubuntu:ubuntu "$NEW_CREDS" || true
  chmod 0600 "$NEW_CREDS" || true
  echo "Migrated admin credentials from PEX cache to $NEW_CREDS"
fi

# --- Create PEX directory ---
PEX_DIR="/home/ubuntu/.local/share/nunet-appliance-web/pex"
mkdir -p "$PEX_DIR"
chown ubuntu:ubuntu "$PEX_DIR" || true
chmod 0700 "$PEX_DIR" || true

# --- TLS: generate self-signed cert on first install (idempotent) ---
SSL_DIR="/etc/nunet-appliance-web/ssl"
SSL_CERT="$SSL_DIR/cert.pem"
SSL_KEY="$SSL_DIR/key.pem"

mkdir -p "$SSL_DIR"
chown ubuntu:ubuntu "$SSL_DIR" || true
chmod 0750 "$SSL_DIR" || true

if [ ! -f "$SSL_CERT" ] || [ ! -f "$SSL_KEY" ]; then
  HOST="$(hostnamectl --static 2>/dev/null || hostname)"
  # Build SAN list: DNS:HOST, DNS:HOST.local plus all non-loopback IPs
  SAN_ENTRIES="DNS:${HOST},DNS:${HOST}.local"
  IPS="$(ip -o addr show scope global | awk '{print $4}' | cut -d/ -f1)"
  for IP in $IPS; do
    SAN_ENTRIES="${SAN_ENTRIES},IP:${IP}"
  done

  OPENSSL_CNF="$(mktemp)"
  cat > "$OPENSSL_CNF" <<OCNF
[req]
default_bits = 2048
prompt = no
default_md = sha256
req_extensions = req_ext
distinguished_name = dn

[dn]
CN = ${HOST}

[req_ext]
subjectAltName = ${SAN_ENTRIES}
OCNF

  umask 077
  openssl req -x509 -nodes -newkey rsa:2048 -days 3650 \
    -keyout "$SSL_KEY" -out "$SSL_CERT" -config "$OPENSSL_CNF" >/dev/null 2>&1 || true
  rm -f "$OPENSSL_CNF"

  chown ubuntu:ubuntu "$SSL_KEY" "$SSL_CERT" || true
  chmod 0600 "$SSL_KEY" || true
  chmod 0640 "$SSL_CERT" || true
fi

# --- Install splash screen script ---
# Ensure directory exists (file is installed by dpkg from package structure)
mkdir -p /home/ubuntu/nunet/appliance/backend/scripts
# Set correct permissions on splash script (installed by dpkg)
if [ -f /home/ubuntu/nunet/appliance/backend/scripts/nunet_boot_splash.py ]; then
  chown ubuntu:ubuntu /home/ubuntu/nunet/appliance/backend/scripts/nunet_boot_splash.py || true
  chmod 0755 /home/ubuntu/nunet/appliance/backend/scripts/nunet_boot_splash.py || true
fi

# --- Update .bashrc with splash screen launcher (only if not already present) ---
if [ -f /home/ubuntu/.bashrc ] && ! grep -q "NuNet Appliance Boot Splash Screen" /home/ubuntu/.bashrc; then
  echo "" >> /home/ubuntu/.bashrc
  echo "# NuNet Appliance Boot Splash Screen" >> /home/ubuntu/.bashrc
  echo "# Show splash screen on login" >> /home/ubuntu/.bashrc
  echo "if [ -f /home/ubuntu/nunet/appliance/backend/scripts/nunet_boot_splash.py ] && [ -t 1 ]; then" >> /home/ubuntu/.bashrc
  echo "    python3 /home/ubuntu/nunet/appliance/backend/scripts/nunet_boot_splash.py 2>/dev/null || true" >> /home/ubuntu/.bashrc
  echo "fi" >> /home/ubuntu/.bashrc
  chown ubuntu:ubuntu /home/ubuntu/.bashrc || true
fi

systemctl daemon-reload
systemctl enable nunet-appliance-web.service >/dev/null 2>&1 || true
systemctl enable --now nunet-appliance-updater.timer >/dev/null 2>&1 || true
systemctl restart nunet-appliance-web.service || true

# Enable and start caddy proxy monitor service
# Ensure wrapper script exists and has correct permissions
if [ -f /usr/lib/nunet-appliance-web/run-caddy-proxy-monitor.sh ]; then
  chmod 0755 /usr/lib/nunet-appliance-web/run-caddy-proxy-monitor.sh || true
  chown ubuntu:ubuntu /usr/lib/nunet-appliance-web/run-caddy-proxy-monitor.sh || true
fi
# Reload systemd to pick up any service file changes
systemctl daemon-reload || true
# Enable service (idempotent - safe if already enabled)
systemctl enable nunet-caddy-proxy-monitor.service >/dev/null 2>&1 || true
# Restart service to use new configuration (will start if not running)
systemctl restart nunet-caddy-proxy-monitor.service || true

exit 0
EOF

cat > "$PKGDIR/DEBIAN/prerm" <<'EOF'
#!/bin/sh -e
if [ "$1" = remove ] || [ "$1" = deconfigure ] || [ "$1" = upgrade ]; then
  systemctl stop nunet-appliance-web.service || true
  systemctl stop nunet-caddy-proxy-monitor.service || true
  systemctl disable --now nunet-appliance-updater.timer >/dev/null 2>&1 || true
  # Clean up PEX cache directory before upgrade
  PEX_DIR="/home/ubuntu/.local/share/nunet-appliance-web/pex"
  if [ -d "$PEX_DIR" ]; then
    rm -rf "$PEX_DIR"/* || true
  fi
fi
exit 0
EOF

cat > "$PKGDIR/DEBIAN/postrm" <<'EOF'
#!/bin/sh -e
systemctl daemon-reload || true
if [ "$1" = purge ]; then
  systemctl disable nunet-appliance-web.service || true
  systemctl disable nunet-caddy-proxy-monitor.service || true
  rm -rf /etc/nunet-appliance-web
fi
exit 0
EOF
chmod 0755 "$PKGDIR/DEBIAN/"{postinst,prerm,postrm}

# build the .deb
OUT="$ROOT/dist"
mkdir -p "$OUT"
dpkg-deb --build --root-owner-group "$PKGDIR" "$OUT/nunet-appliance-web_${VERSION}_${ARCH}.deb"

echo
echo "==> Built: $OUT/nunet-appliance-web_${VERSION}_${ARCH}.deb"
echo "Install:  sudo apt install ./dist/nunet-appliance-web_${VERSION}_${ARCH}.deb"
echo "Status:   systemctl status nunet-appliance-web --no-pager"
echo "Logs:     journalctl -u nunet-appliance-web -f"
