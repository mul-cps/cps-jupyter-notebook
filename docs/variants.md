# Image Variants

Each variant is a separate Dockerfile in `docker/`, built independently by
the CI matrix. All variants except `standard-cpu` are layered on
`docker.io/cschranz/gpu-jupyter:v1.10_cuda-12.9_ubuntu-24.04_slim` (CUDA
12.9 / Ubuntu 24.04); `standard-cpu` uses
`quay.io/jupyter/datascience-notebook:lab-4.5.7` since it has no GPU
requirement.

## standard-cpu (`docker/Dockerfile`)

Base JupyterLab 4.5.7 image with a curated extension set: `jupyterlab-git`,
`nbgitpuller`, `jupyter-resource-usage`, `catppuccin-jupyterlab`,
`jupyterlab-horizon-theme`, `jupyterlab-topbar-text`,
`lckr-jupyterlab-variableinspector`, `jupyterlab-image-editor`, and more. No
GPU, no ROS 2, no desktop — for notebook work that doesn't need CUDA.

## pytorch-code (`docker/Dockerfile.pytorch-code`)

GPU-Jupyter base plus `code-server` (VS Code in the browser) for a combined
notebook + IDE workflow with PyTorch/CUDA available.

## tf-code (`docker/Dockerfile.tf-code`)

Same shape as `pytorch-code`, for TensorFlow workloads instead.

## comfyui (`docker/Dockerfile.comfyui`)

Full [ComfyUI](https://github.com/comfyanonymous/ComfyUI) install (node-based
Stable Diffusion workflows) with ComfyUI Manager pre-installed, exposed
through Jupyter via `jupyter-server-proxy` (see `docker/jupyter-comfyui-proxy/`
for the proxy package) rather than a separate port. GPU-accelerated via the
CUDA base image.

## desktop-ros2 (`docker/Dockerfile.desktop-ros2`)

A full ROS 2 Jazzy desktop environment accessible via TurboVNC/noVNC,
including RViz2 and other GL-heavy tools. GPU-accelerated rendering goes
through **VirtualGL** (`virtualgl_3.1.4_amd64.deb`), with an auto-wrap layer
so users invoke `rviz2`/`rqt` normally and VirtualGL's EGL backend handles
GPU acceleration transparently (no need to type `vglrun` by hand) — this
wraps binaries in place at their own path rather than shadowing them
elsewhere on `PATH`, which is what makes the auto-wrap actually take effect.

## desktop-ros2-xpra (`docker/Dockerfile.desktop-ros2-xpra`)

The same ROS 2 Jazzy desktop, but using **Xpra** (`xpra`, `xpra-x11`,
`xpra-html5`, installed from `xpra.org`'s own apt repo) instead of
TurboVNC/noVNC, for native clipboard support and generally lower-latency
remote desktop than VNC. `start-xpra-desktop.sh` clears
`xfce4-panel.xml`/`xfwm4.xml` on every session start to avoid stale
per-user panel/window-manager state persisting across sessions with a
different viewport size. Same VirtualGL EGL auto-wrap approach as
`desktop-ros2` for GPU-accelerated GL apps.

Both desktop variants support an `INCLUDE_VSCODE_DESKTOP` build arg to
optionally include a full VS Code desktop app in the container (off by
default, to save CI disk space when not needed).
