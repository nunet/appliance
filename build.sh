#!/usr/bin/env bash
set -euo pipefail

# Build script for NuNet Appliance packages
# Builds for the native architecture of the current machine

PKGVERSION="${1:-1.0.0}"
ARCH="$(dpkg --print-architecture)"

echo "Building NuNet Appliance packages v${PKGVERSION} for ${ARCH}"

# Create build directories
mkdir -p dist release/wheels release/frontend-dist
# Ensure proper permissions
chmod 755 dist release release/wheels release/frontend-dist

# Build frontend
echo "Building frontend..."
cd frontend
npm install
npm run build
cd ..

# Build backend
echo "Building backend for ${ARCH}..."
python3 -m venv .build-venv
source .build-venv/bin/activate
pip install -U pip wheel pex

# Build wheels for dependencies
pip wheel -r backend/nunet_api/requirements.txt -w release/wheels

# Build PEX
cd backend
pex -f "../release/wheels" \
    -r nunet_api/requirements.txt \
    -D . \
    -c gunicorn \
    -o "../release/nunet-dms-${ARCH}.pex"
cd ..

# Copy frontend assets
cp -a frontend/dist/. release/frontend-dist/
cp deploy/gunicorn_conf.py release/gunicorn_conf.py

# Build base package
echo "Building base package for ${ARCH}..."
./release/build-base-deb.sh "${PKGVERSION}" "${ARCH}"

# Build web package
echo "Building web package for ${ARCH}..."
./release/new-build-deb.sh "${PKGVERSION}" "${ARCH}"

# Clean up
deactivate
rm -rf .build-venv

echo "Build complete for ${ARCH}"
echo "Packages available in:"
ls -la dist/*.deb
