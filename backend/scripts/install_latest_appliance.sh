#!/bin/bash
set -e

ARCH="$(dpkg --print-architecture)"

echo "Fetching binary for $ARCH architecture"

DEB_URL="https://d.nunet.io/nunet-appliance-web-$ARCH-latest.deb"
TMP_DEB=$(mktemp --suffix=.deb)

trap 'rm -f "$TMP_DEB"' EXIT

echo "Downloading from $DEB_URL..."
wget -q -O "$TMP_DEB" "$DEB_URL"

echo "Installing package..."

sudo DEBIAN_FRONTEND=noninteractive apt-get -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold" -o Debug::pkgProblemResolver=true --reinstall install -f -y "$TMP_DEB"
sudo dpkg --configure -a

echo "Installation complete."
