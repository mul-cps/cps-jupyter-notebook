#!/bin/bash
# Startup script for ComfyUI

set -euo pipefail

echo "Starting ComfyUI..."

# Change to ComfyUI directory
cd /opt/comfyui

# Keep mutable state on the user's persistent volume, rather than in the image.
data_dir="${COMFYUI_DATA_DIR:-${HOME}/.local/share/comfyui}"
mkdir -p "${data_dir}"/{input,output,temp,user}
data_dir="$(cd "${data_dir}" && pwd)"

# Jupyter Server Proxy connects over loopback; expose no unauthenticated LAN port.
exec python main.py --listen 127.0.0.1 --port 8188 \
    --input-directory "${data_dir}/input" \
    --output-directory "${data_dir}/output" \
    --temp-directory "${data_dir}/temp" \
    --user-directory "${data_dir}/user" \
    --database-url "sqlite:///${data_dir}/user/comfyui.db" "$@"
