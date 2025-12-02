#!/bin/bash
set -e

ARCH="$(dpkg --print-architecture)"

echo "Checking for new appliance version for $ARCH..."

DEB_URL="https://d.nunet.io/nunet-appliance-web-$ARCH-latest.deb"
TMP_DEB=$(mktemp --suffix=.deb)

trap 'rm -f "$TMP_DEB"' EXIT

echo "Downloading latest package from $DEB_URL..."
wget -q -O "$TMP_DEB" "$DEB_URL"

echo "Installing package..."

# Run as root, so no sudo.
# Use non-interactive options from existing script to avoid prompts.
# `apt-get install` on a local .deb file will only upgrade if the version is newer.
# The -f flag will attempt to fix any broken dependencies.
DEBIAN_FRONTEND=noninteractive apt-get --reinstall install -f -y \
	-o Dpkg::Options::="--force-confdef" \
	-o Dpkg::Options::="--force-confold" \
	"$TMP_DEB"

dpkg --configure -a

echo "Update check complete."
