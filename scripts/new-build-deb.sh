#!/usr/bin/env bash
set -euo pipefail

# -------- settings you may tweak ----------
VERSION="${1:-1.0.0}"                 # deb version; pass as 1st arg to override
SERVICE_USER="${SERVICE_USER:-ubuntu}" # run the service as this user
# ------------------------------------------

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
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
  echo "ERROR: frontend/dist not found. Run 'npm run build' in ./frontend first."
  exit 1
fi

# --- build backend: wheels + PEX ---
VENV="$ROOT/.build-venv"
python3 -m venv "$VENV"
# shellcheck disable=SC1090
source "$VENV/bin/activate"
python -m pip install -U pip wheel pex

mkdir -p "$ROOT/release/wheels" "$ROOT/release/frontend-dist"
pip wheel -r "$ROOT/backend/nunet_api/requirements.txt" -w "$ROOT/release/wheels"

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
mkdir -p "$PKGDIR/lib/systemd/system"
mkdir -p "$PKGDIR/etc/nunet-appliance-web"

# payload
install -m 0755 "$ROOT/release/nunet-dms.pex" "$PKGDIR/usr/lib/nunet-appliance-web/nunet-dms.pex"
install -m 0644 "$ROOT/release/gunicorn_conf.py" "$PKGDIR/usr/lib/nunet-appliance-web/gunicorn_conf.py"
cp -a "$ROOT/release/frontend-dist/." "$PKGDIR/usr/share/nunet-appliance-web/frontend/dist/"

# (Optional) Data files you want on disk at runtime:
# mkdir -p "$PKGDIR/usr/share/nunet-dms/data"
# cp -a "$ROOT/backend/ensembles" "$PKGDIR/usr/share/nunet-dms/data/" 2>/dev/null || true
# cp -a "$ROOT/backend/plugins"   "$PKGDIR/usr/share/nunet-dms/data/" 2>/dev/null || true
# cp -a "$ROOT/backend/web-assets" "$PKGDIR/usr/share/nunet-dms/data/" 2>/dev/null || true

# default env overrides (editable after install)
cat > "$PKGDIR/etc/nunet-appliance-web/app.env" <<'EOF'
# Overrides for nunet-appliance-web.service (uncomment to change)
#PORT=8080
#WORKERS=2
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
Environment=PORT=8080
Environment=WORKERS=2
Environment=NUNET_STATIC_DIR=/usr/share/nunet-appliance-web/frontend/dist
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
ReadWritePaths=/home/ubuntu/nunet/appliance /home/ubuntu/.cache /home/ubuntu/.nunet/cap /home/nunet/.nunet/cap /home/nunet/config /etc/systemd/system

[Install]
WantedBy=multi-user.target
EOF

# DEBIAN metadata
cat > "$PKGDIR/DEBIAN/control" <<EOF
Package: nunet-appliance-web
Version: ${VERSION}
Section: web
Priority: optional
Architecture: ${ARCH}
Depends: python3 (>= 3.10), systemd
Maintainer: NuNet <maintainer@example.com>
Description: NuNet Appliance Web — FastAPI + React served by Gunicorn/Uvicorn
 Prebuilt PEX + static assets. Installs a systemd service 'nunet-appliance-web'.
EOF

cat > "$PKGDIR/DEBIAN/postinst" <<'EOF'
#!/bin/sh -e
# Create appliance directory with proper permissions
mkdir -p /home/ubuntu/nunet/appliance/known_orgs
mkdir -p /home/ubuntu/nunet/appliance/deployments

chown ubuntu:ubuntu /home/ubuntu/nunet/appliance
chown ubuntu:ubuntu /home/ubuntu/nunet/appliance/known_orgs
chown ubuntu:ubuntu /home/ubuntu/nunet/appliance/deployments

chmod 755 /home/ubuntu/nunet/appliance
chmod 755 /home/ubuntu/nunet/appliance/known_orgs
chmod 755 /home/ubuntu/nunet/appliance/deployments

systemctl daemon-reload
systemctl enable nunet-appliance-web.service >/dev/null 2>&1 || true
systemctl restart nunet-appliance-web.service || true
exit 0
EOF

cat > "$PKGDIR/DEBIAN/prerm" <<'EOF'
#!/bin/sh -e
if [ "$1" = remove ] || [ "$1" = deconfigure ] || [ "$1" = upgrade ]; then
  systemctl stop nunet-appliance-web.service || true
fi
exit 0
EOF

cat > "$PKGDIR/DEBIAN/postrm" <<'EOF'
#!/bin/sh -e
systemctl daemon-reload || true
if [ "$1" = purge ]; then
  systemctl disable nunet-appliance-web.service || true
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