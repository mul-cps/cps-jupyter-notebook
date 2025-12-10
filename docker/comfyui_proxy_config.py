"""
Jupyter Server Proxy configuration for ComfyUI
"""

def setup_comfyui():
    """
    Setup ComfyUI to be proxied through Jupyter Server Proxy
    """
    return {
        'command': ['/home/jovyan/.local/bin/start-comfyui.sh'],
        'timeout': 30,
        'port': 8188,
        'absolute_url': False,
        'launcher_entry': {
            'enabled': True,
            'title': 'ComfyUI',
            'icon_path': '/opt/comfyui/web/assets/favicon.ico',
            'category': 'AI Tools'
        },
        'new_browser_tab': True,
    }

# Register the server proxy
c.ServerProxy.servers = {
    'comfyui': setup_comfyui
}
