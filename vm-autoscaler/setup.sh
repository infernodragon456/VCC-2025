#!/bin/bash

# VM Autoscaler Setup Script
# This script sets up the VM autoscaling environment

echo "===== VM Autoscaler Setup ====="
echo "This script will install the necessary dependencies and set up the autoscaling environment."

# Check if running as root or with sudo
if [ "$EUID" -ne 0 ]; then
  echo "Please run this script with sudo or as root."
  exit 1
fi

# Install system dependencies
echo "Installing system dependencies..."
apt-get update
apt-get install -y docker.io docker-compose python3-pip curl apt-transport-https ca-certificates gnupg

# Install Docker Compose if not installed
if ! command -v docker-compose &> /dev/null; then
    echo "Installing Docker Compose..."
    curl -L "https://github.com/docker/compose/releases/download/v2.12.2/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    chmod +x /usr/local/bin/docker-compose
    ln -s /usr/local/bin/docker-compose /usr/bin/docker-compose
fi

# Add current user to docker group (to avoid having to use sudo with docker)
usermod -aG docker $SUDO_USER

# Install Python dependencies
echo "Installing Python dependencies..."
pip3 install google-cloud-compute google-auth requests

# Check if the service account key exists
echo "Checking for GCP service account key..."
if [ ! -f "service-account-key.json" ]; then
    echo "Warning: service-account-key.json not found."
    echo "You need to provide a GCP service account key with the appropriate permissions."
    echo "Please place your service account key file in the vm-autoscaler directory as 'service-account-key.json'."
fi

# Create directories if they don't exist
echo "Setting up directory structure..."
mkdir -p config app/templates app/static scripts

# Make scripts executable
echo "Making scripts executable..."
chmod +x scripts/autoscaler.py

# Inform the user about the next steps
echo ""
echo "===== Setup Complete ====="
echo "To start the VM autoscaler:"
echo ""
echo "1. Edit scripts/autoscaler.py to update PROJECT_ID with your GCP project ID"
echo "2. Build and start the containers:"
echo "   $ docker-compose up -d"
echo ""
echo "3. Run the autoscaler:"
echo "   $ python3 scripts/autoscaler.py --project-id=YOUR_PROJECT_ID --credentials=./service-account-key.json"
echo ""
echo "To access the demo application:"
echo "   http://localhost:80"
echo ""
echo "To monitor resources:"
echo "   http://localhost:9090 (Prometheus)"
echo ""
echo "To test resource usage, use the buttons on the demo application."
echo "" 