# Storage Model

Every variant follows the same three-tier volume layout, documented in the
repo root as `00_IMPORTANT_STORAGE_WARNING.md` and `01_CLUSTER_GUIDE.md`.

| Path | Persistence | Purpose |
|---|---|---|
| `/home/jovyan` | **Persistent** | User settings, VS Code extensions, Jupyter config (`.jupyter`, `.config`). Don't put large datasets or build artifacts here — it's not tuned for heavy I/O. |
| `/home/jovyan/work` | **Ephemeral** | High-performance scratch. All data here is lost on container restart — active computation, compiling, large dataset processing belongs here. |
| `/home/jovyan/shared` | **Shared** | Mounted for exchanging files with other users/services. |

## Recommended workflow

1. Clone repositories into `/home/jovyan/work` for fast git operations and builds.
2. Install extensions / configure VS Code — settings persist automatically in `/home/jovyan`.
3. Copy results you want to keep into `/home/jovyan` or `/home/jovyan/shared` before stopping the container.

## Docker Compose / manual run example

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

`/home/jovyan/work` can also be a `tmpfs` mount for maximum I/O speed on
ephemeral, throwaway scratch (e.g. compiling a ROS 2 workspace).

## Read-only home mounts

If `/home/jovyan` is mounted **read-only** (e.g. a Kubernetes
`volumeMounts.readOnly: true`), a pre-notebook hook
(`docker/00-prepare-readonly-home.sh`, baked into every variant) runs first
and:

- exports `JUPYTER_ENV_VARS_TO_UNSET` (prevents an unbound-variable failure
  in the base image's own `start.sh`)
- detects the read-only mount and logs it
- ensures runtime directories that must be writable actually are

`docker/fix-permissions.sh` was also hardened to degrade gracefully on a
read-only home: it tries a full recursive `chown` first, falls back to
`find -writable` for a selective fix if that fails, and always exits `0` so
a read-only mount never blocks container startup. This is why containers
start cleanly whether `/home/jovyan` is writable or read-only — no
configuration needed on either side.
