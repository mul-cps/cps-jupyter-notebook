# Important Storage Warning

## Persistence
- **`/home/jovyan`**: This directory is **PERSISTENT**.
  - It contains your user settings, VS Code extensions, and configuration files.
  - **DO NOT** store large datasets or temporary build files here, as it may be slower than ephemeral storage.

- **`/home/jovyan/work`**: This directory is **EPHEMERAL**.
  - It is designed for high-performance I/O.
  - **ALL DATA HERE IS LOST** when the container is restarted.
  - Use this for active computation, compiling code, or processing large datasets.

- **`/home/jovyan/shared`**: This directory is **SHARED**.
  - Use this to share files with other users or services.
  - It is mounted at `/home/jovyan/shared`.

## Recommended Workflow
1. **Clone repositories** into `/home/jovyan/work` for fast git operations and builds.
2. **Install extensions** and configure VS Code; these settings will be saved in `/home/jovyan` automatically.
3. **Copy important results** to `/home/jovyan` or `/home/jovyan/shared` before stopping the container.
