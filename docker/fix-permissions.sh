#!/bin/bash
set -e

# Fix permissions for .config and work directories
# These might be mounted as root by Docker/K8s
# Use || true to handle read-only filesystems gracefully

if [ -d "/home/${NB_USER}/.config" ]; then
    echo "Fixing permissions for /home/${NB_USER}/.config"
    chown -R "${NB_USER}:users" "/home/${NB_USER}/.config" 2>/dev/null || {
        # If chown fails (e.g., read-only mount), try to fix what we can
        find "/home/${NB_USER}/.config" -writable -exec chown "${NB_USER}:users" {} + 2>/dev/null || true
    }
fi

if [ -d "/home/${NB_USER}/work" ]; then
    echo "Fixing permissions for /home/${NB_USER}/work"
    chown -R "${NB_USER}:users" "/home/${NB_USER}/work" 2>/dev/null || {
        # If chown fails (e.g., read-only mount), try to fix what we can
        find "/home/${NB_USER}/work" -writable -exec chown "${NB_USER}:users" {} + 2>/dev/null || true
    }
fi

# Test if we can write to the directories (non-fatal check)
for dir in "/home/${NB_USER}/.config" "/home/${NB_USER}/work"; do
    if [ -d "$dir" ]; then
        if touch "$dir/.write-test" 2>/dev/null; then
            rm -f "$dir/.write-test"
            echo "✓ Directory $dir is writable"
        else
            echo "⚠ Directory $dir is read-only (this is expected for some mounts)"
        fi
    fi
done


