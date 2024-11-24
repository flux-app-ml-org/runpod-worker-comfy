#!/bin/bash

# Directory for custom nodes
CUSTOM_NODES_DIR="/comfyui/custom_nodes"

# Create directory if it doesn't exist
mkdir -p $CUSTOM_NODES_DIR

# Read each line from custom_nodes.txt
while IFS= read -r repo_url; do
    # Skip empty lines and comments
    [[ -z "$repo_url" || "$repo_url" =~ ^# ]] && continue

    # Extract the repo name from the URL
    repo_name=$(basename "$repo_url" .git)

    # Clone the repository
    git clone "$repo_url" "$CUSTOM_NODES_DIR/$repo_name"

    # Check if requirements.txt exists and install
    if [ -f "$CUSTOM_NODES_DIR/$repo_name/requirements.txt" ]; then
        pip3 install -r "$CUSTOM_NODES_DIR/$repo_name/requirements.txt"
    fi
done < /workflows/custom_nodes.txt
