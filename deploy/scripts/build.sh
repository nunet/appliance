#!/usr/bin/env bash
set -exuo pipefail

# Build script for NuNet Appliance packages
# Builds for the native architecture of the current machine

# Resolve repository root from deploy/scripts
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

RAW_VERSION="$(git describe --tags --always --abbrev=0 --dirty 2>/dev/null || echo "0.0.0")"
APPLIANCE_VERSION="$(printf '%s' "$RAW_VERSION" | sed -E 's/^v|r//')"
PKGVERSION="$(printf '%s' "$APPLIANCE_VERSION" | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -n1 || true)"
if [ -z "$PKGVERSION" ]; then
    PKGVERSION="${PACKAGE_VERSION_FALLBACK:-0.0.0}"
    echo "Warning: semantic version tag not found from '$RAW_VERSION'; using package version '$PKGVERSION'."
fi

# Generate version file for backend
echo "__version__ = \"${PKGVERSION}\"" > "$ROOT/backend/_version.py"

ARCH="$(dpkg --print-architecture)"

echo "Building NuNet Appliance packages ${PKGVERSION} for ${ARCH}"

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

# Install Node.js 22+ (NodeSource preferred, tarball fallback)
install_node() {
    if command -v node >/dev/null 2>&1 && node --version | grep -qE "v(22|24)"; then
        echo "Node.js $(node --version) already satisfies requirement"
        return 0
    fi

    echo "Installing Node.js 22+ from NodeSource..."
    if curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash - && \
       sudo apt-get install -y nodejs; then
        echo "Node.js installed via NodeSource"
        return 0
    fi

    echo "NodeSource unavailable, falling back to official Node.js tarball..."
    local fallback_version="${NODE_FALLBACK_VERSION:-22.21.1}"
    local arch="${ARCH:-$(dpkg --print-architecture)}"
    local node_arch=""
    case "$arch" in
        amd64|x86_64)
            node_arch="linux-x64"
            ;;
        arm64|aarch64)
            node_arch="linux-arm64"
            ;;
        armhf|armv7l)
            node_arch="linux-armv7l"
            ;;
        *)
            echo "Unsupported architecture for Node.js tarball fallback: $arch" >&2
            return 1
            ;;
    esac
    local tarball="node-v${fallback_version}-${node_arch}.tar.xz"
    local url="https://nodejs.org/dist/v${fallback_version}/${tarball}"
    curl -fsSLO "$url"
    sudo tar -C /usr/local --strip-components=1 -xJf "$tarball"
    rm -f "$tarball"
    echo "Node.js ${fallback_version} installed from tarball"
}

install_node

# Create build directories
mkdir -p "$ROOT/dist" "$ROOT/release/wheels" "$ROOT/release/frontend-dist"
# Ensure proper permissions
chmod 755 "$ROOT/dist" "$ROOT/release" "$ROOT/release/wheels" "$ROOT/release/frontend-dist"

PNPM_VERSION="${PNPM_VERSION:-10.4.0}"
PNPM_CMD=(corepack pnpm)
corepack prepare "pnpm@${PNPM_VERSION}" --activate

# Build frontend
echo "Building frontend..."
( cd "$ROOT/frontend" && \
    "${PNPM_CMD[@]}" install --frozen-lockfile && \
    ("${PNPM_CMD[@]}" audit --prod || true) && \
    if "${PNPM_CMD[@]}" ls @swc/core --depth -1 >/dev/null 2>&1; then \
      echo "Rebuilding @swc/core from source for host CPU..." && \
      npm_config_build_from_source=true "${PNPM_CMD[@]}" rebuild @swc/core; \
    fi && \
    "${PNPM_CMD[@]}" run build )

# Build backend
echo "Building backend for ${ARCH}..."
python3 -m venv "$SCRIPT_DIR/.build-venv"
# shellcheck disable=SC1090
source "$SCRIPT_DIR/.build-venv/bin/activate"
export PIP_DEFAULT_TIMEOUT="${PIP_DEFAULT_TIMEOUT:-120}"
export PIP_RETRIES="${PIP_RETRIES:-5}"
python -m pip install --no-cache-dir --progress-bar off --upgrade pip wheel pex

# Build wheels for dependencies
python -m pip wheel --no-cache-dir --progress-bar off -r "$ROOT/backend/nunet_api/requirements.txt" -w "$ROOT/release/wheels"

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
