#!/usr/bin/env bash
set -euo pipefail

# Build script for NuNet Appliance packages
# Builds for the native architecture of the current machine

PKGVERSION="${1:-1.0.0}"
ARCH="$(dpkg --print-architecture)"

# Resolve repository root from deploy/scripts
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "Building NuNet Appliance packages v${PKGVERSION} for ${ARCH}"

# Install system dependencies
echo "Installing system dependencies..."
sudo apt-get update
sudo apt-get install -y \
    build-essential \
    cargo \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    wget \
    curl \
    gnupg \
    ca-certificates \
    dpkg-dev \
    fakeroot \
    debhelper \
    devscripts

# Install Node.js 20+ from NodeSource
echo "Installing Node.js 20+ from NodeSource..."
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs

# Create build directories
mkdir -p "$ROOT/dist" "$ROOT/release/wheels" "$ROOT/release/frontend-dist"
# Ensure proper permissions
chmod 755 "$ROOT/dist" "$ROOT/release" "$ROOT/release/wheels" "$ROOT/release/frontend-dist"

# Build frontend
echo "Building frontend..."
( cd "$ROOT/frontend" && \
    npm install && \
    (npm audit fix || true) && \
    if npm ls @swc/core >/dev/null 2>&1; then \
      echo "Rebuilding @swc/core from source for host CPU..." && \
      npm rebuild @swc/core --build-from-source; \
    fi && \
    npm run build )

# Build backend
echo "Building backend for ${ARCH}..."
python3 -m venv "$SCRIPT_DIR/.build-venv"
# shellcheck disable=SC1090
source "$SCRIPT_DIR/.build-venv/bin/activate"
pip install -U pip wheel pex

# Build wheels for dependencies
pip wheel -r "$ROOT/backend/nunet_api/requirements.txt" -w "$ROOT/release/wheels"

# Build PEX
( cd "$ROOT/backend" && \
  pex -f "$ROOT/release/wheels" \
      -r nunet_api/requirements.txt \
      -D . \
      -c gunicorn \
      -o "$ROOT/release/nunet-dms-${ARCH}.pex" )

# Copy frontend assets
cp -a "$ROOT/frontend/dist/." "$ROOT/release/frontend-dist/"
cp "$ROOT/deploy/gunicorn_conf.py" "$ROOT/release/gunicorn_conf.py"

# Build base package
echo "Building base package for ${ARCH}..."
"$SCRIPT_DIR/build-base-deb.sh" "${PKGVERSION}" "${ARCH}"

# Build web package
echo "Building web package for ${ARCH}..."
"$SCRIPT_DIR/build-web-deb.sh" "${PKGVERSION}" "${ARCH}"

# Clean up
deactivate
rm -rf "$SCRIPT_DIR/.build-venv"

echo "Build complete for ${ARCH}"
echo "Packages available in:"
ls -la "$ROOT/dist"/*.deb

