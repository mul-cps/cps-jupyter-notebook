# Read-Only Home Mount Fail-Safety Implementation

## Problem Summary
When Jupyter notebooks are launched with read-only mounts on `/home/jovyan`, the initialization fails with two issues:

1. **Read-only filesystem errors**: Permission fix script fails when trying to `chown` files on read-only mounted paths
   ```
   chown: changing ownership of '/home/jovyan/.config/dask/distributed.yaml': Read-only file system
   ```

2. **Unbound variable**: The base image's `start.sh` script references an undefined variable
   ```
   /usr/local/bin/start.sh: line 20: JUPYTER_ENV_VARS_TO_UNSET: unbound variable
   ```

## Solution Implemented

### 1. Enhanced Permission Fix Script (`fix-permissions.sh`)
**Changes:**
- Added graceful error handling for read-only filesystems
- Uses `find -writable` to only modify accessible files when full directory chown fails
- Suppresses error messages to prevent noise
- Added informational checks to detect and report read-only mounts
- Always exits with `0` (success) to prevent container startup failure

**Key features:**
```bash
# Try full recursive chown first
chown -R "${NB_USER}:users" "/path" 2>/dev/null || {
    # Fallback: only fix writable files
    find "/path" -writable -exec chown ... {} + 2>/dev/null || true
}
```

### 2. New Pre-Notebook Hook (`00-prepare-readonly-home.sh`)
**Purpose:** Prepare environment before Jupyter starts
**Location:** `/usr/local/bin/before-notebook.d/00-prepare-readonly-home.sh`

**Functionality:**
- Ensures `JUPYTER_ENV_VARS_TO_UNSET` is defined (prevents unbound variable error)
- Detects read-only mounts by testing file creation
- Ensures critical runtime directories have correct permissions
- Provides informative logging about mount status
- Runs as root before the notebook server starts

**Hook naming convention:**
- `00-` prefix ensures it runs first (before `10-gpu-checks.sh` and `10-fix-permissions.sh`)
- All hooks are sourced in alphabetical order by the base image

### 3. Updated Dockerfiles
Modified all five Dockerfiles to include the new hook:
- `Dockerfile` (standard CPU)
- `Dockerfile.pytorch-code`
- `Dockerfile.tf-code`
- `Dockerfile.desktop-ros2`
- `Dockerfile.comfyui`

**Changes:**
```dockerfile
# Copy pre-notebook hooks
COPY 00-prepare-readonly-home.sh /usr/local/bin/before-notebook.d/
COPY fix-permissions.sh /usr/local/bin/before-notebook.d/
RUN chmod +x /usr/local/bin/before-notebook.d/*.sh
```

## Hook Execution Order
1. **`00-prepare-readonly-home.sh`** - Prepare environment, set variables, detect mounts
2. **`10-gpu-checks.sh`** - GPU/VGL diagnostics (already existed)
3. **`10-fix-permissions.sh`** - Fix permissions with graceful error handling
4. **Jupyter notebook starts**

## Benefits

✅ **Robust handling of read-only mounts** - No startup failures on read-only home directories
✅ **Graceful degradation** - Works whether mounts are read-write or read-only
✅ **Early variable initialization** - Prevents unbound variable errors
✅ **Informative logging** - Users can see which mounts are read-only
✅ **Backward compatible** - Doesn't break existing setups with writable mounts
✅ **Consistent across all variants** - All container types get the same protection

## Testing the Fix

### Test Scenario 1: Read-Only Mount
```bash
docker run -it --rm \
  -v home-volume:/home/jovyan:ro \
  -v /tmp/work:/home/jovyan/work \
  your-image:latest jupyterhub-singleuser
```
Expected: Container starts successfully despite read-only home

### Test Scenario 2: Normal Writable Mount
```bash
docker run -it --rm \
  -v home-volume:/home/jovyan \
  your-image:latest jupyterhub-singleuser
```
Expected: Container starts with permissions fixed normally

### Test Scenario 3: Mixed Mounts
```bash
docker run -it --rm \
  -v home-volume:/home/jovyan:ro \
  -v work-volume:/home/jovyan/work:rw \
  your-image:latest jupyterhub-singleuser
```
Expected: Container starts with work directory writable, home read-only

## Files Modified

1. **`docker/fix-permissions.sh`** - Enhanced with better error handling
2. **`docker/00-prepare-readonly-home.sh`** - NEW: Pre-notebook preparation hook
3. **`docker/Dockerfile`** - Added hook copies
4. **`docker/Dockerfile.pytorch-code`** - Added hook copies
5. **`docker/Dockerfile.tf-code`** - Added hook copies
6. **`docker/Dockerfile.desktop-ros2`** - Added hook copies
7. **`docker/Dockerfile.comfyui`** - Added hook copies

## Notes for Deployment

- These changes are **backward compatible** and require no configuration changes
- The new hook runs in alphabetical order as part of the standard Jupyter initialization
- Error suppression with `|| true` ensures one failed chown doesn't crash the startup
- The solution works with any combination of read-only and read-write mounts
- Original container behavior is preserved for standard deployments

## Kubernetes Deployment Example

```yaml
volumeMounts:
  - name: home
    mountPath: /home/jovyan
    readOnly: true  # Now safe to use!
  - name: work
    mountPath: /home/jovyan/work
    readOnly: false

volumes:
  - name: home
    persistentVolumeClaim:
      claimName: user-home
  - name: work
    emptyDir: {}  # or tmpfs mount
```

The container will now start gracefully with this configuration.
