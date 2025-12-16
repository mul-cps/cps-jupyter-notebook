#!/usr/bin/env bash
# Pre-notebook.d hook to prepare environment for read-only home mounts
# This runs as root before the notebook server starts
set -euo pipefail

echo "[prepare-readonly-home] Starting read-only home preparation..."

# Ensure JUPYTER_ENV_VARS_TO_UNSET is set (may be used by start.sh)
export JUPYTER_ENV_VARS_TO_UNSET="${JUPYTER_ENV_VARS_TO_UNSET:-}"

# Check if home directories are mounted read-only
for dir in "/home/${NB_USER}" "/home/${NB_USER}/.config" "/home/${NB_USER}/.jupyter" "/home/${NB_USER}/.local"; do
    if [ -d "$dir" ]; then
        # Check if directory is read-only by trying to touch a test file
        if ! touch "$dir/.ro-test-$$" 2>/dev/null; then
            echo "[prepare-readonly-home] ⚠ Detected read-only mount: $dir"
            # Continue anyway - we'll handle this gracefully in subsequent scripts
        else
            rm -f "$dir/.ro-test-$$"
        fi
    fi
done

# Ensure critical runtime directories exist and are writable (if possible)
# These are typically ephemeral mounts or should be writable
for dir in "/home/${NB_USER}/.cache" "/run/user/$(id -u ${NB_USER} 2>/dev/null || echo 1000)"; do
    if [ -d "$dir" ]; then
        chmod 700 "$dir" 2>/dev/null || true
        chown "${NB_USER}:users" "$dir" 2>/dev/null || true
    fi
done

echo "[prepare-readonly-home] ✓ Read-only home preparation complete"
exit 0
