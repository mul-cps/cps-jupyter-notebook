#!/bin/bash
# Startup script for ComfyUI

set -e

echo "Starting ComfyUI..."

# Change to ComfyUI directory
cd /opt/comfyui

# Start ComfyUI with proper configuration
# --listen 0.0.0.0 allows connections from jupyter-server-proxy
# --port 8188 is the default ComfyUI port
exec python main.py --listen 0.0.0.0 --port 8188
