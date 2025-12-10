# ComfyUI Jupyter Notebook Integration

This Docker image integrates [ComfyUI](https://github.com/comfyanonymous/ComfyUI) with JupyterHub, providing a complete AI image generation environment accessible through Jupyter's web interface.

## Features

- **ComfyUI**: Full installation of ComfyUI for node-based stable diffusion workflows
- **ComfyUI Manager**: Pre-installed for easy management of custom nodes and models
- **Jupyter Integration**: Access ComfyUI through jupyter-server-proxy
- **JupyterLab Extensions**: Includes git, resource monitoring, and code-server integration
- **GPU Support**: Built on PyTorch with CUDA support for GPU acceleration

## What's Included

### Base Components
- JupyterLab 4.2.1
- PyTorch with CUDA support
- Python 3.x with scientific computing libraries

### ComfyUI Components
- ComfyUI (latest from main branch)
- ComfyUI Manager for custom nodes management
- Pre-configured jupyter-server-proxy integration

### Development Tools
- code-server (VS Code in browser)
- Git and GitHub CLI
- btop for system monitoring
- SSH server for remote access

## Usage

### Accessing ComfyUI

Once your Jupyter environment is running, you can access ComfyUI in two ways:

1. **Through Jupyter Launcher**: Click on the "ComfyUI" icon in the JupyterLab launcher
2. **Direct URL**: Navigate to `/comfyui/` relative to your Jupyter server URL

Example: If your Jupyter is at `https://jupyter.example.com/user/yourname/`, ComfyUI will be at `https://jupyter.example.com/user/yourname/comfyui/`

### Installing Models

ComfyUI models are stored in `/opt/comfyui/models/`. You can add models in several ways:

1. **Using ComfyUI Manager**: 
   - Open ComfyUI in your browser
   - Click on "Manager" button
   - Browse and install models directly

2. **Manual Upload**:
   - Use JupyterLab's file browser to upload models to `/opt/comfyui/models/checkpoints/`
   - Or use the terminal to download models with `wget` or `curl`

3. **From Notebook**:
   ```python
   import os
   from huggingface_hub import hf_hub_download
   
   # Example: Download a model from Hugging Face
   model_path = "/opt/comfyui/models/checkpoints/"
   hf_hub_download(
       repo_id="runwayml/stable-diffusion-v1-5",
       filename="v1-5-pruned-emaonly.safetensors",
       local_dir=model_path
   )
   ```

### Using ComfyUI with Python

You can also interact with ComfyUI programmatically from Jupyter notebooks:

```python
import requests
import json

# ComfyUI API endpoint (local)
COMFYUI_URL = "http://localhost:8188"

# Example: Queue a prompt
def queue_prompt(prompt):
    p = {"prompt": prompt}
    data = json.dumps(p).encode('utf-8')
    response = requests.post(f"{COMFYUI_URL}/prompt", data=data)
    return response.json()

# Your workflow JSON here
workflow = {...}
result = queue_prompt(workflow)
print(f"Queued with ID: {result['prompt_id']}")
```

## Building the Image

### Using GitHub Actions (Recommended)

The image is automatically built when you push to the main branch:

```bash
git add .
git commit -m "Update ComfyUI configuration"
git push origin main
```

The built image will be available at:
```
ghcr.io/<your-username>/cps-jupyter-notebook:latest-comfyui
```

### Building Locally

```bash
cd docker
docker build -f Dockerfile.comfyui -t comfyui-jupyter:latest .
```

### Building with Secrets (for password protection)

```bash
cd docker
docker build -f Dockerfile.comfyui \
  --secret id=root_password,src=<(echo "your-password") \
  -t comfyui-jupyter:latest .
```

## Configuration

### Proxy Configuration

The ComfyUI proxy is configured in `comfyui_proxy_config.py`. Key settings:

- **Port**: 8188 (ComfyUI default)
- **Launcher Entry**: Enabled with custom icon
- **New Browser Tab**: Opens in a new tab by default

### ComfyUI Settings

ComfyUI runs with the following settings:
- Listen address: `0.0.0.0` (allows proxy access)
- Port: `8188`
- Working directory: `/opt/comfyui`

You can customize ComfyUI by editing `/opt/comfyui/extra_model_paths.yaml` or other config files.

## Deployment with JupyterHub

To use this image with JupyterHub, update your JupyterHub configuration:

```python
c.KubeSpawner.profile_list = [
    {
        'display_name': 'ComfyUI Environment',
        'description': 'JupyterLab with ComfyUI for AI image generation',
        'kubespawner_override': {
            'image': 'ghcr.io/<your-username>/cps-jupyter-notebook:latest-comfyui',
        }
    }
]
```

### Resource Requirements

Recommended minimum resources:
- **CPU**: 2 cores
- **RAM**: 8GB
- **GPU**: NVIDIA GPU with 8GB+ VRAM (for stable diffusion models)
- **Storage**: 50GB+ (models can be large)

## Troubleshooting

### ComfyUI Not Starting

Check the logs:
```bash
# In a Jupyter terminal
journalctl --user -u comfyui
# Or check the process
ps aux | grep comfyui
```

### Out of Memory Errors

If you encounter OOM errors:
1. Use smaller models or lower resolution
2. Enable CPU offloading in ComfyUI settings
3. Request more resources from your JupyterHub admin

### Models Not Found

Ensure models are in the correct directory:
```bash
ls -la /opt/comfyui/models/checkpoints/
```

## Advanced Usage

### Custom Nodes

Install custom nodes using ComfyUI Manager or manually:

```bash
cd /opt/comfyui/custom_nodes
git clone <custom-node-repo-url>
cd <custom-node-name>
pip install -r requirements.txt
```

### Sharing Models Between Users

If deploying on JupyterHub, you can configure shared model storage using `extra_model_paths.yaml`:

```yaml
shared_models:
    base_path: /shared/comfyui/models/
    checkpoints: checkpoints/
    vae: vae/
    loras: loras/
```

## References

- [ComfyUI Documentation](https://docs.comfy.org/)
- [ComfyUI GitHub](https://github.com/comfyanonymous/ComfyUI)
- [ComfyUI Manager](https://github.com/ltdrdata/ComfyUI-Manager)
- [Jupyter Server Proxy](https://jupyter-server-proxy.readthedocs.io/)

## License

This image builds upon:
- Jupyter Docker Stacks (BSD 3-Clause)
- ComfyUI (GPL-3.0)
- ComfyUI Manager (GPL-3.0)

Please ensure compliance with all component licenses when using this image.
