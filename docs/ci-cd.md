# CI/CD Pipeline

`.github/workflows/docker-publish.yml` builds and publishes every image
variant to `ghcr.io/mul-cps/cps-jupyter-notebook`, but only rebuilds the
variants that actually need it.

## Path-filtered matrix

The `check-changes` job uses `dorny/paths-filter` to detect which
Dockerfile(s) changed:

- If a **shared** file under `docker/` (anything that isn't a
  `docker/Dockerfile*`) or the workflow file itself changed, **all six
  variants** rebuild — a shared hook script or base config change could
  affect every image.
- Otherwise, only the variant(s) whose own Dockerfile changed get added to
  the build matrix (`standard-cpu`, `pytorch-code`, `tf-code`,
  `desktop-ros2`, `desktop-ros2-xpra`, `comfyui`).

If no variant matched (e.g. a docs-only change), `build-and-push` is
skipped entirely via
`if: fromJson(needs.check-changes.outputs.matrix).variant[0] != null`.

## Build and push

Each matched variant builds independently in the `build-and-push` matrix
job:

- `docker/setup-qemu-action` + `docker/setup-buildx-action` for the build
- `docker/login-action` to GHCR using the workflow's own `GITHUB_TOKEN`
- `docker/metadata-action` computes tags: `latest-<suffix>` on `main`,
  branch-ref and tag-ref variants, and a `sha-<suffix>` tag for every build
- `docker/build-push-action` builds `linux/amd64` only, using GitHub
  Actions' own cache backend (`type=gha`), and pushes only on
  non-`pull_request` events (PRs build but don't push)
- Two build secrets (`admin_password`, `root_password`) are passed through
  from repo secrets (`CPS_JUPYTER_ADMIN_PASSWORD`,
  `CPS_JUPYTER_ROOT_PASSWORD`) for whichever Dockerfile stages need them

A disk-cleanup step runs first on the GitHub-hosted runner (removing
preinstalled Android/`.NET`/Swift/GHC toolchains, the runner's swap file,
and pruning the local Docker system) since the GPU-Jupyter base images plus
CUDA layers are large relative to the runner's default disk.

## Job summary

Every build run appends a small table to the GitHub Actions job summary
(variant name, Dockerfile path, resulting tags) so you can see at a glance
what was built without digging through logs.
