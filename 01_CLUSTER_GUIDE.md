# Cluster Guide

## Storage Configuration

To ensure optimal performance and persistence, configure your container volumes as follows:

### Docker Command Example

```bash
docker run -it --rm \
  -p 8888:8888 \
  --user root \
  -e GRANT_SUDO=yes \
  -v my-home-volume:/home/jovyan \
  -v /tmp/work:/home/jovyan/work \
  -v /path/to/shared:/home/jovyan/shared \
  my-jupyter-image
```

### Explanation

1.  **`/home/jovyan` (Persistent)**:
    *   Mount a named volume or a persistent host directory here.
    *   This preserves your shell history, VS Code extensions (`.vscode`), and Jupyter configuration (`.jupyter`).

2.  **`/home/jovyan/work` (Ephemeral)**:
    *   Mount a fast, local temporary directory or use a `tmpfs` mount.
    *   Example: `--mount type=tmpfs,destination=/home/jovyan/work`
    *   This ensures that heavy I/O operations (like compiling ROS 2 workspaces) are fast.

3.  **`/home/jovyan/shared` (Shared)**:
    *   Mount a shared network drive or host directory here to exchange files.

## Notes
- The container is configured to fix permissions on `/home/jovyan/.config` and `/home/jovyan/work` at startup.
- Ensure that the mounted volumes have appropriate permissions or allow the container to change them (running as root initially helps with this).
