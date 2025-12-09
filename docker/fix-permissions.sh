#!/bin/bash
set -e

# Fix permissions for .config and work directories
# These might be mounted as root by Docker/K8s
if [ -d "/home/${NB_USER}/.config" ]; then
    echo "Fixing permissions for /home/${NB_USER}/.config"
    chown -R "${NB_USER}:users" "/home/${NB_USER}/.config" || true
fi

if [ -d "/home/${NB_USER}/work" ]; then
    echo "Fixing permissions for /home/${NB_USER}/work"
    chown -R "${NB_USER}:users" "/home/${NB_USER}/work" || true
fi
