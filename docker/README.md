# CPS Jupyter Notebook Docker Images

This repository builds two variants of the Jupyter Notebook image:

## Variants

### CPU-only (`-cpu` suffix)
- **Base Image**: `quay.io/jupyter/datascience-notebook:lab-4.2.1`
- **Dockerfile**: `Dockerfile.cpu`
- **Platforms**: `linux/amd64`, `linux/arm64`
- **Use Case**: General-purpose data science work without GPU requirements
- **Tag Examples**: 
  - `ghcr.io/mul-cps/cps-jupyter-notebook:main-cpu`
  - `ghcr.io/mul-cps/cps-jupyter-notebook:latest-cpu`

### CUDA GPU (`-cuda-12.6` suffix)
- **Base Image**: `cschranz/gpu-jupyter:v1.9_cuda-12.6_ubuntu-24.04_slim`
- **Dockerfile**: `Dockerfile.gpu`
- **Platforms**: `linux/amd64`
- **CUDA Version**: 12.6
- **Features**: 
  - NVIDIA GPU support
  - jupyterlab-nvdashboard for GPU monitoring
- **Use Case**: GPU-accelerated data science, machine learning, and deep learning
- **Tag Examples**: 
  - `ghcr.io/mul-cps/cps-jupyter-notebook:main-cuda-12.6`
  - `ghcr.io/mul-cps/cps-jupyter-notebook:latest-cuda-12.6`

## Features

Both variants include:
- JupyterLab 4.2.1+
- Git integration (jupyterlab-git)
- nbgitpuller for easy repository cloning
- Resource usage monitoring
- Themes: Catppuccin and Horizon
- SSH and proxy server support
- VS Code Server integration via jupyter-code-server
- Glances system monitoring
- Additional tools: gh (GitHub CLI), btop, nodejs

## Building Locally

### CPU-only variant
```bash
docker build -f docker/Dockerfile.cpu -t cps-jupyter:cpu ./docker
```

### GPU variant
```bash
docker build -f docker/Dockerfile.gpu -t cps-jupyter:cuda ./docker
```

## Running

### CPU-only variant
```bash
docker run -p 8888:8888 ghcr.io/mul-cps/cps-jupyter-notebook:latest-cpu
```

### GPU variant (requires NVIDIA Docker runtime)
```bash
docker run --gpus all -p 8888:8888 ghcr.io/mul-cps/cps-jupyter-notebook:latest-cuda-12.6
```

## CI/CD Pipeline

The GitHub Actions workflow uses a matrix strategy to build both variants in parallel:
- Each variant has its own cache scope for optimal build performance
- Multi-platform support (CPU variant supports both amd64 and arm64)
- Automatic tagging based on branch, PR, semver, and SHA
- Image signing with cosign for security
- Only CUDA variant built for amd64 (GPU support requirement)

## Requirements

### For GPU variant:
- NVIDIA GPU with CUDA 12.6+ support
- NVIDIA Docker runtime installed
- nvidia-container-toolkit configured
