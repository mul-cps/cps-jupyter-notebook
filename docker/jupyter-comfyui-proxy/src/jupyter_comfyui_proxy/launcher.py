"""Nonprivileged ComfyUI process launcher used by Jupyter Server Proxy."""
import os
from pathlib import Path
import sys


def main():
    """Replace this process with ComfyUI, preserving the inherited environment."""
    print('Starting ComfyUI...', flush=True)
    os.chdir(os.environ.get('COMFYUI_PATH') or '/opt/comfyui')
    # Resolve relative overrides after chdir, matching the former shell launcher.
    data_dir = Path(os.environ.get('COMFYUI_DATA_DIR') or
                    str(Path(os.environ['HOME']) / '.local/share/comfyui'))
    for name in ('input', 'output', 'temp', 'user'):
        (data_dir / name).mkdir(parents=True, exist_ok=True)
    data_dir = Path(os.path.abspath(data_dir))
    command = [
        'python', 'main.py', '--listen', '127.0.0.1', '--port', '8188',
        '--input-directory', str(data_dir / 'input'),
        '--output-directory', str(data_dir / 'output'),
        '--temp-directory', str(data_dir / 'temp'),
        '--user-directory', str(data_dir / 'user'),
        '--database-url', 'sqlite:///' + str(data_dir / 'user/comfyui.db'),
        *sys.argv[1:],
    ]
    os.execvp(command[0], command)


if __name__ == '__main__':
    main()
