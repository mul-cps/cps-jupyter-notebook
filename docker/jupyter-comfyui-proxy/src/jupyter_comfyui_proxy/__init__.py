import os

_HERE = os.path.dirname(os.path.abspath(__file__))

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
            'icon_path': os.path.join(_HERE, 'icons/comfyui.svg'),
            'category': 'AI Tools'
        },
        'new_browser_tab': True,
    }
