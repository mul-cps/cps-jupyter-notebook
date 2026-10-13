"""Verify the installed offline compute overlay, including asset ownership."""
import base64
import hashlib
from importlib import metadata
import json
from pathlib import Path
import sys


def verify():
    import cps_compute
    import ipykernel
    import jupyter_collaboration
    import papermill

    marker = 'labextensions/@cps/compute-jupyterlab/'
    owners = []
    for distribution in metadata.distributions():
        name = distribution.metadata['Name'].lower().replace('_', '-').replace('.', '-')
        assert name != 'cps-compute-hub', 'Hub package installed in notebook runtime'
        if name == 'cps-compute':
            assert not any('cps_compute/labextension/' in str(file) for file in distribution.files or ()), 'Old SDK bundles Lab assets'
        assets = [file for file in distribution.files or () if marker in str(file)]
        if not assets:
            continue
        owners.append(name)
        assert name == 'cps-compute-jupyterlab', 'Unexpected Lab asset owner: ' + name
        for file in assets:
            data = distribution.locate_file(file).read_bytes()
            digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip('=')
            assert file.hash and file.hash.mode == 'sha256' and file.hash.value == digest, 'Installed Lab asset hash differs'
            assert file.size == len(data), 'Installed Lab asset size differs'
    assert owners == ['cps-compute-jupyterlab'], 'Separate Lab distribution must own the extension'
    version = metadata.version('cps-compute')
    assert metadata.version('cps-compute-jupyterlab') == version, 'Compute co-release versions differ'
    package = Path(sys.prefix) / 'share/jupyter/labextensions/@cps/compute-jupyterlab/package.json'
    content = json.loads(package.read_text())
    assert content['name'] == '@cps/compute-jupyterlab' and content['version'].replace('-rc.', 'rc') == version, 'Installed addon identity differs'


if __name__ == '__main__':
    verify()
