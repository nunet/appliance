#!/bin/bash

if [ -d "/home/ubuntu/.nunet" ] && [ "$(ls -A /home/ubuntu/.nunet)" ]; then
    echo "⚠️ WARNING: An existing NuNet DMS configuration was detected in ~/.nunet."
    
    # Ask user whether to overwrite or cancel
    while true; do
        read -p "Do you want to overwrite the existing configuration? (y/n): " choice
        case "$choice" in
            y|Y ) 
                TIMESTAMP=$(date +%Y%m%d-%H%M%S)
                BACKUP_DIR="/home/ubuntu/.nunet_backup_$TIMESTAMP"
                
                echo "📂 Moving existing configuration to $BACKUP_DIR..."
                mv "/home/ubuntu/.nunet" "$BACKUP_DIR"
                echo "✅ Backup complete. Proceeding with new configuration..."
                break
                ;;
            n|N ) 
                echo "❌ Installation canceled by user."
                exit 1
                ;;
            * ) echo "Invalid input. Please enter y (yes) or n (no).";;
        esac
    done
fi


# Create A random passphrase for DMS context
# Define the number of words in the passphrase
NUM_WORDS=3
SEPARATOR="-"

# Check if the system has a dictionary file
if [ ! -f "/usr/share/dict/words" ]; then
    echo "❌ Dictionary file not found! Falling back to built-in words."
    WORD_LIST=("apple" "banana" "cherry" "delta" "echo" "foxtrot" "gamma" "hotel" "india" "juliet" "kilo" "lima" "mango" "november" "oscar" "papa" "quebec" "romeo" "sierra" "tango" "uniform" "victor" "whiskey" "xray" "yankee" "zulu")
else
    # Use system word list
    WORD_LIST=($(shuf -n 1000 /usr/share/dict/words | grep -E '^[a-zA-Z]{3,}$'))
fi

# Select random words
PASS_PHRASE=""
for i in $(seq 1 $NUM_WORDS); do
    WORD=${WORD_LIST[$RANDOM % ${#WORD_LIST[@]}]}
    # Capitalize the first letter
    FORMATTED_WORD="$(tr '[:lower:]' '[:upper:]' <<< ${WORD:0:1})${WORD:1}"
    if [ -z "$PASS_PHRASE" ]; then
        PASS_PHRASE="$FORMATTED_WORD"
    else
        PASS_PHRASE="$PASS_PHRASE$SEPARATOR$FORMATTED_WORD"
    fi
done

# Output the generated passphrase
echo "🔐 Your DMS Passphrase is: $PASS_PHRASE"
echo "Write this down and keep it somewhere safe better still use a password manager to store it"
# Update Passphrase in keystore
keyctl add user dms_passphrase "$PASS_PHRASE" @u
# Keystore
keyctl list @u
# Make persistant on reboot
echo "$PASS_PHRASE" > /home/ubuntu/.secrets/dms_passphrase
# keyctl pipe $(keyctl request user dms_passphrase) > /home/ubuntu/.secrets/dms_passphrase
chmod 600 /home/ubuntu/.secrets/dms_passphrase

export DMS_PASSPHRASE=$PASS_PHRASE
# Create new DMS context using the new random passphrase
DMS_DID=$(nunet key new dms)
nunet cap new dms
echo "This is your DMS DID: $DMS_DID"
export DMS_DID=$DMS_DID

echo "DMS Configuration script has run if you see a DID above then it's golden"

echo "Copy DMS Config to nunet home directory"
rm /home/nunet/.nunet/key/dms.json
rm /home/nunet/.nunet/cap/dms.cap
cp /home/ubuntu/.nunet/key/dms.json /home/nunet/.nunet/key/
cp /home/ubuntu/.nunet/cap/dms.cap /home/nunet/.nunet/cap/
echo "Check permissions for nunet user"
ls -al /home/nunet/.nunet/key/
ls -al /home/nunet/.nunet/cap/
echo "$PASS_PHRASE" > /home/nunet/.secrets/dms_passphrase
echo "Done!"



