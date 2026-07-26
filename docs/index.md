# CPS JupyterHub Notebook Images

This repository builds the JupyterHub single-user notebook images used on the
`cit-cps-gpu` cluster. It's a set of Dockerfiles — one per variant — layered
on top of upstream Jupyter/GPU base images, plus a CI pipeline that builds and
publishes each variant to GHCR whenever its Dockerfile changes.

## What's here

- **`docker/`** — one Dockerfile per notebook variant (standard CPU,
  PyTorch+code-server, TensorFlow+code-server, ComfyUI, and two ROS 2 desktop
  variants), plus shared startup hooks (`fix-permissions.sh`,
  `00-prepare-readonly-home.sh`) baked into every variant.
- **`.github/workflows/docker-publish.yml`** — path-filtered matrix build:
  only the variants whose Dockerfile actually changed get rebuilt, unless a
  shared file or the workflow itself changed, in which case everything
  rebuilds.

See **[Image Variants](variants.md)** for what each one provides,
**[Storage Model](storage.md)** for the persistent/ephemeral/shared volume
layout every variant follows, and **[CI/CD Pipeline](ci-cd.md)** for how
builds are triggered and published.

## Quick links

- Images: `ghcr.io/mul-cps/cps-jupyter-notebook:<tag>` (see
  [CI/CD Pipeline](ci-cd.md) for the tagging scheme)
- Deployed via JupyterHub profiles on the `cit-cps-gpu` cluster (see
  `mul-cps/cps-gpu-cluster`, `cluster-maintenance/.../user/jupyter/jupyterhub`)
