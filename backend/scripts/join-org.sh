#!/bin/bash

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Get DMS passphrase from keyring
export DMS_PASSPHRASE=$(keyctl pipe $(keyctl request user dms_passphrase) 2>/dev/null)
CONFIG_FILE="$HOME/.config/nunet/menu_config.json"

# Maximum number of retries for wormhole send
MAX_RETRIES=3
# Delay between retries in seconds
RETRY_DELAY=30

load_status() {
    if [ -f "$CONFIG_FILE" ]; then
        # Read DID from JSON using jq
        DMS_DID=$(jq -r '.dms_did' "$CONFIG_FILE")
    else
        echo "No config file found - DID is not available"
        exit 1
    fi
}

# Function to send DID via wormhole with retries
send_did_via_wormhole() {
    local code="$1"
    local did="$2"
    local attempt=1
    
    while [ $attempt -le $MAX_RETRIES ]; do
        echo "Attempt $attempt of $MAX_RETRIES to send DID via wormhole..."
        
        # Try to send the DID
        if wormhole send --code "$code" <<< "$did"; then
            echo "✅ DID sent successfully!"
            return 0
        else
            local exit_code=$?
            echo "❌ Wormhole send failed with exit code $exit_code"
            
            if [ $attempt -lt $MAX_RETRIES ]; then
                echo "Waiting $RETRY_DELAY seconds before retrying..."
                sleep $RETRY_DELAY
            fi
        fi
        
        ((attempt++))
    done
    
    echo "❌ Failed to send DID after $MAX_RETRIES attempts"
    return 1
}

# Load current status to get DID
load_status

if [ -z "$DMS_DID" ] || [ "$DMS_DID" = "null" ] || [ "$DMS_DID" = "Unknown" ]; then
    echo "Error: DMS DID not found. Please make sure DMS is initialized and running."
    exit 1
fi

clear
echo "==================================================="
echo "Network Join Process"
echo "==================================================="

echo
echo "Steps to joining the network:"
echo "1. Your DMS DID will be shared with the Organization Admin."
echo "2. You'll receive a code (format: number-word1-word2)."
echo "3. The Admin will authorize your request."
echo "4. Share this code with the Admin securely (e.g. via a Discord support ticket)."
echo "5. Keep this terminal open while waiting for approval."
echo


# Ask for confirmation
read -p "Ready to proceed? (yes/no): " confirm
if [[ ! "$confirm" =~ ^[Yy] ]]; then
    echo "Process cancelled."
    exit 0
fi

echo
echo "---------------------------------------------------"
echo "⚠️  When you see the code below, copy it"
echo "---------------------------------------------------"
echo

# Generate wormhole code
WORMHOLE_CODE=$("$HOME/menu/scripts/generate-wormhole-code.sh")

if [ -z "$WORMHOLE_CODE" ]; then
    echo "Error: Failed to generate wormhole code."
    exit 1
fi

echo
echo -e "${YELLOW}Your code is: $WORMHOLE_CODE.${NC} Share this code securely with the Organisation's Admin."
echo
echo "🔄 Sending your DID to the Organisation's Admin"
echo "This may take up to 24 hours while the organization admin processes your request."
echo "DO NOT CLOSE THIS TERMINAL!"
echo "==================================================="

# Send DID via wormhole with retry logic
if ! send_did_via_wormhole "$WORMHOLE_CODE" "$DMS_DID"; then
    echo "❌ Failed to send DID. Please try again later."
    exit 1
fi

echo
echo "==================================================="
echo "Waiting for first access token (require capability)..."
echo "DO NOT CLOSE THIS TERMINAL!"
echo "==================================================="

# Wait for the Org ID 
ORG_DID=$(wormhole receive "$WORMHOLE_CODE")

if [ -z "$ORG_DID" ]; then
    echo "Error: No org did received."
    exit 1
fi

# Security check: Is this a known organization?
if ! grep -q "^$ORG_DID:" "/home/ubuntu/nunet/appliance/known_orgs/known_orgs.txt"; then
    echo -e "${RED}⚠️ WARNING: This organization is NOT in the known list.${NC}"
    echo "Unknown Organization DID: $ORG_DID"
    echo "This could pose a security risk."
    read -p "Are you sure you want to apply capabilities from this unknown organization? (yes/no): " confirm
    if [[ ! "$confirm" =~ ^[Yy] ]]; then
        echo "❌ Operation cancelled by user."
        exit 1
    fi
else
    echo -e "${GREEN}✅ This is a known organization.${NC}"
fi

echo "✅ Received Org DID"
GRANT_EXPIRY_DATE=$(date -d '+30 days' --utc +%Y-%m-%dT%H:%M:%SZ)
REQUIRE_TOKEN=$(nunet cap grant --context dms --cap /dms/deployment --cap /dms/tokenomics/contract --cap /broadcast --cap /public --topic /nunet --expiry $GRANT_EXPIRY_DATE $ORG_DID)
echo "🔄 Applying require token..."
nunet cap anchor -c dms --require "$REQUIRE_TOKEN"
echo "✅ Require token applied successfully"


# Wait for the second token (provide) using the same code
echo
echo "==================================================="
echo "Waiting for second access token (provide capability)..."
echo "==================================================="

PROVIDE_TOKEN=$(wormhole receive "$WORMHOLE_CODE")

if [ -z "$PROVIDE_TOKEN" ]; then
    echo "Error: No access token received."
    exit 1
fi

echo "✅ Received second token"
echo "🔄 Applying provide token..."
nunet cap anchor -c dms --provide "$PROVIDE_TOKEN"
echo "✅ Provide token applied successfully"

# Wait for the third token (Elasticsearch API key) using the same code
echo
echo "==================================================="
echo "Waiting for Elasticsearch API key..."
echo "==================================================="

ELASTIC_API_KEY=$(wormhole receive "$WORMHOLE_CODE")

if [ -z "$ELASTIC_API_KEY" ]; then
    echo "Error: No Elasticsearch API key received."
    exit 1
fi

echo "✅ Received Elasticsearch API key"
echo "🔄 Applying Elasticsearch API key..."
nunet --config "/home/nunet/config/dms_config.json" config set observability.elasticsearch_api_key "$ELASTIC_API_KEY"
nunet --config "/home/nunet/config/dms_config.json" config set observability.elasticsearch_enabled "true"
nunet --config "/home/nunet/config/dms_config.json" config set observability.elasticsearch_url "https://telemetry.nunet.io"

echo "✅ Elasticsearch API key applied successfully"

# Wait for the fourth transfer (certificates) using the same code
echo
echo "==================================================="
echo "Waiting for certificates..."
echo "==================================================="

# Create a directory for the certificates
CERT_DIR="$HOME/nunet/appliance/ddns-client/certs"
mkdir -p "$CERT_DIR"

# Remove existing certs.tar if it exists
if [ -f "$CERT_DIR/certs.tar" ]; then
    echo "Removing existing certs.tar..."
    rm -f "$CERT_DIR/certs.tar"
fi

# Remove existing certs directory if it exists
if [ -d "$CERT_DIR/certs" ]; then
    echo "Removing existing certs directory..."
    rm -rf "$CERT_DIR/certs"
fi

# Verify directory is clean
echo "Verifying directory is clean..."
ls -la "$CERT_DIR"

# Receive the certificate tar file
echo "🔄 Receiving certificate bundle..."
wormhole receive --output-file "$CERT_DIR/certs.tar" "$WORMHOLE_CODE"

if [ ! -s "$CERT_DIR/certs.tar" ]; then
    echo "Error: Certificate bundle is empty."
    exit 1
fi

echo "✅ Received certificate bundle"
echo "🔄 Extracting certificates..."

# Extract the certificates
(cd "$CERT_DIR" && tar -xf certs.tar)

# Verify the certificates were extracted
if [ ! -d "$CERT_DIR/certs" ]; then
    echo "Error: Certificates directory not found after extraction."
    exit 1
fi

echo "✅ Certificates extracted successfully"
echo "Certificate files:"
ls -l "$CERT_DIR/certs"

echo
echo "Current capabilities for DMS context:"
nunet cap list -c dms
echo
echo "Do you want to copy these to the currently running DMS ?"
# Ask for confirmation
read -p "Ready to proceed? (yes/no): " confirm
if [[ ! "$confirm" =~ ^[Yy] ]]; then
    echo "Capabilities have not been copied to DMS but are available to $USER."
    exit 0
fi
echo "Copying new capabilities to nunet user"
sudo cp /home/ubuntu/.nunet/cap/dms.cap /home/nunet/.nunet/cap/
sudo chown nunet:nunet /home/nunet/.nunet/cap/dms.cap 

# Verify file integrity using checksums
src_hash=$(sha256sum "/home/ubuntu/.nunet/cap/dms.cap" | awk '{print $1}')
dest_hash=$(sudo sha256sum "/home/nunet/.nunet/cap/dms.cap" | awk '{print $1}')

if [[ "$src_hash" == "$dest_hash" ]]; then
    echo -e "${GREEN}Capabilities file copy verified successfully. Checksums match.${NC}"
else
    echo -e "${RED}Capabilities file verification failed! Checksums do not match.${NC}"
    exit 2
fi

echo "Users current capability directory"
ls -al /home/nunet/.nunet/cap/

echo
echo "==================================================="
echo -e "✅ ${GREEN}Network Join Process Complete!${NC}"
echo "==================================================="
echo "You can now close this terminal and return to the menu"
echo "==================================================="

# Wait for user acknowledgment
read -p "Press Enter to continue..."
