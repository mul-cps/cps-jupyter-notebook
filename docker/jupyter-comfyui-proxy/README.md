# Jupyter ComfyUI Proxy

The `comfyui` Jupyter Server Proxy entry point exposes the ComfyUI launcher in
JupyterLab. The installed `jupyter-comfyui-launcher` console script replaces its
own process with `python main.py`, binds to loopback port 8188, and forwards
additional command arguments unchanged. It uses the inherited PATH and environment
and runs as the current notebook user; it performs no privilege or GPU setup.

Configuration is through environment variables:

- `COMFYUI_PATH`: installed application directory (default `/opt/comfyui`).
- `COMFYUI_DATA_DIR`: persistent input, output, temp and user directory (default
  `$HOME/.local/share/comfyui`). Relative overrides resolve from the application
  directory, preserving the earlier launcher behavior.

The launcher creates the four state directories and uses
`sqlite:///<absolute-data-directory>/user/comfyui.db`. Application dependencies,
ComfyUI-Manager and filesystem permissions remain image responsibilities.

Build wheel and sdist with `python -m build`. Run the subprocess contract tests
with `python -m unittest discover -s tests -v` from this package directory.
