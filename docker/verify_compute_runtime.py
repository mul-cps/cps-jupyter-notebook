"""Verify the installed offline compute overlay, including asset ownership."""
import base64
import hashlib
from importlib import metadata
import json
from pathlib import Path
import sys


def verify_hera():
    """Render the ordinary Hera snippet pattern offline; never submit a workflow."""
    from hera.workflows import Container, Resources, Workflow

    assert metadata.version('hera-workflows') == '7.1.0', 'Notebook runtime requires Hera7.1.0'
    with Workflow(name='runtime-verification', entrypoint='main') as workflow:
        template = Container(
            name='main', image='runtime-verification:not-submitted',
            command=['python', '-c'], args=["print('offline verification')"],
            resources=Resources(cpu_request='1', cpu_limit='1',
                                memory_request='1Gi', memory_limit='1Gi'),
        )
    assert isinstance(template, Container), 'Snippet must produce an ordinary Hera template'
    rendered = workflow.to_dict()['spec']['templates'][0]['container']
    assert rendered['resources']['limits'] == {'cpu': '1', 'memory': '1Gi'}, 'Hera fixed resources differ'
    assert rendered['resources']['requests'] == {'cpu': '1', 'memory': '1Gi'}, 'Hera fixed requests differ'


def verify_browser_hook():
    """Check installed operator hook custody without an identity/network request."""
    import cps_compute_jupyterlab
    from types import SimpleNamespace
    from unittest.mock import patch
    import os
    assert cps_compute_jupyterlab._jupyter_server_extension_points() == [{'module': 'cps_compute_jupyterlab'}], 'Packaged server discovery required'
    config = Path(sys.prefix) / 'etc/jupyter/jupyter_server_config.d/cps_compute_jupyterlab.json'
    assert json.loads(config.read_text()) == {'ServerApp': {'jpserver_extensions': {'cps_compute_jupyterlab': True}}}, 'Packaged auto-enable configuration required'
    for source in ['cps', 'cit']:
        path = '/teaching/services/' + source + '-admin/api/compute/v1/'
        settings = {'page_config_hook': lambda handler, page: {**page, 'other': 'preserved'}}
        with patch.dict(os.environ, {'CPS_COMPUTE_BROWSER_GATEWAY_PATH': path}, clear=True):
            cps_compute_jupyterlab._load_jupyter_server_extension(SimpleNamespace(web_app=SimpleNamespace(settings=settings)))
        value = settings['page_config_hook'](None, {'cpsComputeGatewayUrl': 'https://untrusted.invalid/'})
        assert value == {'cpsComputeGatewayUrl': path, 'other': 'preserved'}, 'Installed trusted routing hook differs'


def verify():
    import cps_compute
    import ipykernel
    import jupyter_collaboration
    import papermill

    verify_hera()
    verify_browser_hook()

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
