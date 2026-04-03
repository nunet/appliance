#!/bin/bash
set -e

ARCH="$(dpkg --print-architecture)"
ENVIRONMENT="${APPLIANCE_ENV:-production}"
DRY_RUN="${NUNET_UPDATER_DRY_RUN:-0}"

case "$ARCH" in
  amd64|arm64) ;;
  *)
    echo "Unsupported architecture: $ARCH" >&2
    exit 2
    ;;
esac

case "$ENVIRONMENT" in
  production)
    PREFERRED_CHANNEL="stable"
    FALLBACK_CHANNEL="latest"
    ;;
  staging)
    PREFERRED_CHANNEL="latest"
    FALLBACK_CHANNEL=""
    ;;
  *)
    echo "Invalid APPLIANCE_ENV='$ENVIRONMENT'. Expected 'production' or 'staging'." >&2
    exit 2
    ;;
esac

build_url() {
  local channel="$1"
  echo "https://d.nunet.io/nunet-appliance-web-${ARCH}-${channel}.deb"
}

url_exists() {
  local url="$1"
  wget --spider -q "$url" >/dev/null 2>&1
}

RESOLVED_CHANNEL="$PREFERRED_CHANNEL"
FELL_BACK="false"
PREFERRED_URL="$(build_url "$PREFERRED_CHANNEL")"

if ! url_exists "$PREFERRED_URL" && [ -n "$FALLBACK_CHANNEL" ]; then
  FALLBACK_URL="$(build_url "$FALLBACK_CHANNEL")"
  if url_exists "$FALLBACK_URL"; then
    RESOLVED_CHANNEL="$FALLBACK_CHANNEL"
    FELL_BACK="true"
  fi
fi

RESOLVED_URL="$(build_url "$RESOLVED_CHANNEL")"

if [ "$DRY_RUN" = "1" ]; then
  echo "environment=$ENVIRONMENT"
  echo "component=appliance"
  echo "arch=$ARCH"
  echo "channel=$PREFERRED_CHANNEL"
  echo "resolved_channel=$RESOLVED_CHANNEL"
  echo "fell_back=$FELL_BACK"
  echo "url=$RESOLVED_URL"
  exit 0
fi

# --- Run plugin lifecycle sync (root-owned) ---
if [ -x /usr/lib/nunet-appliance-web/plugin-manager.sh ]; then
  /usr/lib/nunet-appliance-web/plugin-manager.sh sync || \
    echo "Plugin manager sync failed; continuing with appliance update." >&2
fi

echo "Checking for new appliance version for $ARCH (env=$ENVIRONMENT, channel=$PREFERRED_CHANNEL)..."

TMP_DEB=$(mktemp --suffix=.deb)

trap 'rm -f "$TMP_DEB"' EXIT

attempt_channels=("$PREFERRED_CHANNEL")
if [ -n "$FALLBACK_CHANNEL" ] && [ "$FALLBACK_CHANNEL" != "$PREFERRED_CHANNEL" ]; then
  attempt_channels+=("$FALLBACK_CHANNEL")
fi

last_error="No update channel attempt completed"
for channel in "${attempt_channels[@]}"; do
  DEB_URL="$(build_url "$channel")"
  echo "Downloading package from $DEB_URL..."
  if ! wget -q -O "$TMP_DEB" "$DEB_URL"; then
    last_error="Download failed for channel=$channel"
    echo "$last_error" >&2
    continue
  fi

  echo "Installing package from channel=$channel..."
  if DEBIAN_FRONTEND=noninteractive apt-get --reinstall --allow-downgrades install -f -y \
      -o Dpkg::Options::="--force-confdef" \
      -o Dpkg::Options::="--force-confold" \
      "$TMP_DEB"; then
    dpkg --configure -a
    echo "Update check complete."
    exit 0
  fi

  last_error="Installation failed for channel=$channel"
  echo "$last_error" >&2
done

echo "$last_error" >&2
exit 1
