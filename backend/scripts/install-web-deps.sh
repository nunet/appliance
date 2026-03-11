#!/bin/bash

# Exit on error
set -e

echo "Installing required packages for web interface..."

# Update package list
sudo apt-get update

# Install Python packages
sudo apt-get install -y \
    python3-flask \
    python3-flask-limiter \
    python3-openssl \
    python3-cryptography \
    python3-qrcode

echo "Packages installed successfully!" 

# Create the jobs directory if it doesn't exist
sudo mkdir -p /home/nunet/nunet/jobs       

# Set ownership
sudo chown -R nunet:nunet /home/nunet/nunet

# Set safe traversal/listing on parent dirs only (non-recursive)
sudo chmod 750 /home/nunet
sudo chmod 750 /home/nunet/nunet

# Set full group access to jobs dir
sudo chmod 770 /home/nunet/nunet/jobs       

# Set setgid so new files inherit the nunet group
sudo chmod g+s /home/nunet/nunet/jobs       

echo "Updated permissions for nunet jobs directory"