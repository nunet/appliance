#!/bin/bash

# Update package list
apt update

# Install required packages
apt install -y wget
apt install -y --no-install-recommends python3
apt install -y python3-pip # Ensure pip is installed for pip install commands
apt install -y openssh-server

# start SSH server
service ssh start

# checking the status of ssh
echo "Confirming SSH server is running"
service ssh status

# --- Create LLM directory and move into it ---
echo "Creating directory 'LLM' and moving into it..."
mkdir LLM # -p ensures parent directories are created if they don't exist
cd LLM
echo "Current directory: $(pwd)" # Verify current directory

# Download the fine-tuner script
echo "Downloading fine tuning script.."
wget https://gitlab.com/nunet/solutions/ml-on-nunet/ml-on-gpu-service/-/raw/develop/demos-and-pocs/personal-ai-1/LLM-fine-tuning/ft-llama3.2-1b-dms-readme-alpaca-packing.py

# Download the requirements file
echo "Downloading requirements.txt.."
wget https://gitlab.com/nunet/solutions/ml-on-nunet/ml-on-gpu-service/-/raw/develop/demos-and-pocs/personal-ai-1/LLM-fine-tuning/requirements.txt

# Download the dataset
wget https://gitlab.com/nunet/solutions/ml-on-nunet/ml-on-gpu-service/-/raw/develop/demos-and-pocs/personal-ai-1/LLM-fine-tuning/dms_readme_alpaca.jsonl

# Install dependencies
echo "Installing Python dependencies"
pip install bitsandbytes>=0.41.1
pip install peft>=0.5.0
pip install flash-attn --extra-index-url https://download.pytorch.org/whl/cu126

#Authenticate to huggingface
echo "Authenticating to Hugging Face..."
huggingface-cli login --token $HF_TOKEN

# Print installed versions for verification
echo "Installed package versions (filtered) :"
pip list | grep -E "bitsandbytes|peft|accelerate|transformers|flash-attn|tensorboard|datasets|tqdm"

echo "Provision Script execution complete."
