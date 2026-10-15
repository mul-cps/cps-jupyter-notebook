"""Bounded offline CPS CPU package qualification; no live API or GPU calls."""
import argparse
import base64
import asyncio
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import re
import ssl
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch
from urllib.request import Request, urlopen

EXPECTED = {
    'cps-compute': '0.1.0', 'cps-compute-jupyterlab': '0.1.0',
    'jupyterhub': '5.4.6', 'jupyterlab': '4.5.7',
    'jupyter-collaboration': '4.4.2', 'jupyter-server-ydoc': '2.4.2',
    'jupyter-ydoc': '3.5.0', 'pycrdt': '0.13.1',
    'hera-workflows': '7.1.0', 'papermill': '2.7.0',
}
ENTRY = 'static/remoteEntry.c7eaea5553822765e8f8.js'
HOOK_SHA = 'd04e877ca16e39eb05fc52cf02fc9d5846c5253ba9d2c8f8252f56afbb6c564f'
VISITOR_PATH = '/services/cps-compute-ui/api/compute/v1/'


def packages_and_hook():
    versions = {name: metadata.version(name) for name in EXPECTED}
    assert versions == EXPECTED, versions
    import cps_compute
    from cps_compute import sdk
    import cps_compute_jupyterlab as addon
    import jupyter_collaboration
    import jupyter_server_ydoc
    import pycrdt
    import ipykernel
    import numpy
    import pandas
    import scipy
    import sklearn
    assert numpy.add(1, 2) == 3
    assert callable(sdk.client)
    public_ca = ssl.DER_cert_to_PEM_cert(ssl.create_default_context().get_ca_certs(binary_form=True)[0])
    with patch.dict(os.environ, {
        'CPS_COMPUTE_URL': 'https://gateway.invalid',
        'CPS_COMPUTE_HUB': 'cps',
        'CPS_COMPUTE_TOKEN': 'offline-process-only-fixture',
        'CPS_COMPUTE_CA_PEM': public_ca,
    }, clear=True):
        with sdk.client() as client:
            assert client.base_url.scheme == 'https' and client.base_url.host == 'gateway.invalid'
            assert client.headers['X-CPS-Hub'] == 'cps'
            assert client.trust_env is False
            assert client._transport._pool._ssl_context.verify_mode == ssl.CERT_REQUIRED
    assert hashlib.sha256(Path(addon.__file__).read_bytes()).hexdigest() == HOOK_SHA
    assert addon._jupyter_server_extension_points() == [{'module': 'cps_compute_jupyterlab'}]
    settings = {'page_config_hook': lambda handler, page: {**page, 'existing': 'preserved'}}
    with patch.dict(os.environ, {'CPS_COMPUTE_BROWSER_GATEWAY_PATH': VISITOR_PATH}, clear=True):
        addon._load_jupyter_server_extension(SimpleNamespace(web_app=SimpleNamespace(settings=settings)))
        asyncio.run(addon._start_jupyter_server_extension(SimpleNamespace(web_app=SimpleNamespace(settings=settings))))
    assert settings['page_config_hook'](None, {}) == {
        'existing': 'preserved', 'cpsComputeGatewayUrl': VISITOR_PATH,
    }
    absent = {}
    with patch.dict(os.environ, {}, clear=True):
        addon._load_jupyter_server_extension(SimpleNamespace(web_app=SimpleNamespace(settings=absent)))
    assert not absent, 'No source/endpoint may be silently assumed'
    for module, filename in [('cps_compute_jupyterlab', 'cps_compute_jupyterlab.json'),
                             ('jupyter_server_ydoc', 'jupyter_collaboration.json')]:
        config = Path(sys.prefix) / 'etc/jupyter/jupyter_server_config.d' / filename
        value = json.loads(config.read_text())
        assert value['ServerApp']['jpserver_extensions'][module] is True
    package = Path(sys.prefix) / 'share/jupyter/labextensions/@cps/compute-jupyterlab/package.json'
    data = json.loads(package.read_text())
    assert data['jupyterlab']['_build']['load'] == ENTRY
    assert (package.parent / ENTRY).is_file()
    owners = []
    for name in ['cps-compute', 'cps-compute-jupyterlab']:
        dist = metadata.distribution(name)
        assets = [item for item in dist.files or () if 'labextensions/@cps/compute-jupyterlab/' in str(item)]
        if assets:
            owners.append(name)
        if name == 'cps-compute':
            assert not any('labextension' in str(item) for item in dist.files or ()), 'SDK still owns legacy Lab assets'
        for item in dist.files or ():
            path = dist.locate_file(item)
            assert path.is_file(), str(item)
            if item.hash:
                assert item.hash.mode == 'sha256'
                digest = base64.urlsafe_b64encode(hashlib.sha256(path.read_bytes()).digest()).decode().rstrip('=')
                assert item.hash.value == digest and item.size == path.stat().st_size, str(item)
    assert owners == ['cps-compute-jupyterlab'], owners
    assert sorted(path.name for path in (package.parent / 'static').glob('remoteEntry.*.js')) == [Path(ENTRY).name]
    try:
        metadata.distribution('cps-compute-hub')
    except metadata.PackageNotFoundError:
        pass
    else:
        raise AssertionError('Hub adapter must not be installed in notebook image')
    return versions


def hera_and_notebooks():
    from hera.workflows import Container, Resources, Workflow
    import nbformat
    import papermill
    from papermill.exceptions import PapermillExecutionError
    with Workflow(name='offline-cps-cpu-qualification', entrypoint='main') as workflow:
        Container(name='main', image='example.invalid/offline@sha256:' + '1' * 64,
                  command=['python', '-c'], args=['print(42)'],
                  resources=Resources(cpu_request='1', cpu_limit='1',
                                      memory_request='1Gi', memory_limit='1Gi'))
    resources = workflow.to_dict()['spec']['templates'][0]['container']['resources']
    assert resources == {'requests': {'cpu': '1', 'memory': '1Gi'},
                         'limits': {'cpu': '1', 'memory': '1Gi'}}
    with tempfile.TemporaryDirectory(prefix='cps-cpu-papermill-') as td:
        root = Path(td)
        notebook = nbformat.v4.new_notebook(cells=[
            nbformat.v4.new_code_cell('count = 1\nvalues = {"enabled": False}',
                                     metadata={'tags': ['parameters']}),
            nbformat.v4.new_code_cell('assert count == 3 and values == {"enabled": True}\nprint(count)'),
        ], metadata={'kernelspec': {'name': 'python3', 'display_name': 'Python 3', 'language': 'python'}})
        nbformat.write(notebook, root / 'input.ipynb')
        papermill.execute_notebook(str(root / 'input.ipynb'), str(root / 'executed.ipynb'),
                                  parameters={'count': 3, 'values': {'enabled': True}},
                                  kernel_name='python3', progress_bar=False)
        assert not nbformat.read(root / 'executed.ipynb', as_version=4).metadata.papermill.exception
        notebook.cells[-1].source = 'raise ValueError("controlled offline failure")'
        nbformat.write(notebook, root / 'failure.ipynb')
        try:
            papermill.execute_notebook(str(root / 'failure.ipynb'), str(root / 'failed-executed.ipynb'),
                                      kernel_name='python3', progress_bar=False)
        except PapermillExecutionError:
            failed = nbformat.read(root / 'failed-executed.ipynb', as_version=4)
            assert failed.metadata.papermill.exception
        else:
            raise AssertionError('Controlled notebook failure was not retained')
    return {'hera_serialization': 'passed', 'typed_papermill_success': 'passed',
            'failed_executed_notebook_retained': 'passed'}


def server_probe(browser_path=VISITOR_PATH):
    # This is a local-only test credential generated in the test process, not baked.
    import secrets
    token = secrets.token_urlsafe(24)
    env = dict(os.environ, CPS_COMPUTE_BROWSER_GATEWAY_PATH=browser_path)
    env.update(JUPYTER_RUNTIME_DIR='/tmp/qualification-runtime', JUPYTER_DATA_DIR='/tmp/qualification-data',
               JUPYTER_CONFIG_DIR='/tmp/qualification-config', IPYTHONDIR='/tmp/qualification-ipython',
               XDG_CACHE_HOME='/tmp/qualification-cache')
    for key in list(env):
        if key.startswith(('JUPYTERHUB_', 'CPS_COMPUTE_')) and key != 'CPS_COMPUTE_BROWSER_GATEWAY_PATH':
            del env[key]
    with tempfile.TemporaryDirectory(prefix='cps-cpu-server-') as td:
        log = Path(td) / 'server.log'
        with log.open('w') as stream:
            proc = subprocess.Popen([
                sys.executable, '-m', 'jupyterlab', '--no-browser',
                '--ServerApp.ip=127.0.0.1', '--ServerApp.port=8899',
                '--ServerApp.port_retries=0', '--ServerApp.root_dir=/home/jovyan',
                '--IdentityProvider.token=' + token,
            ], env=env, stdout=stream, stderr=subprocess.STDOUT)
            try:
                body = None
                for _ in range(120):
                    if proc.poll() is not None:
                        raise AssertionError('Local server exited: ' + log.read_text().replace(token, '<redacted>'))
                    try:
                        req = Request('http://127.0.0.1:8899/lab', headers={'Authorization': 'token ' + token})
                        with urlopen(req, timeout=1) as response:
                            body = response.read().decode()
                        break
                    except OSError:
                        time.sleep(0.5)
                assert body is not None, 'Local JupyterLab startup timed out'
                match = re.search(r'<script[^>]*id="jupyter-config-data"[^>]*>(.*?)</script>', body, re.S)
                assert match, 'Actual HTML PageConfig missing'
                page = json.loads(match.group(1))
                assert page['cpsComputeGatewayUrl'] == browser_path
                extensions = {x['name'] for x in page['federated_extensions']}
                assert '@cps/compute-jupyterlab' in extensions
                assert '@jupyter/collaboration-extension' in extensions
                req = Request('http://127.0.0.1:8899/lab/extensions/@cps/compute-jupyterlab/' + ENTRY,
                              headers={'Authorization': 'token ' + token})
                with urlopen(req, timeout=5) as response:
                    served = response.read()
                installed = Path(sys.prefix) / 'share/jupyter/labextensions/@cps/compute-jupyterlab' / ENTRY
                assert served == installed.read_bytes(), 'Actual served prebuilt entry differs'
                logs = log.read_text()
                for name in ['cps_compute_jupyterlab', 'jupyter_server_ydoc']:
                    assert re.search(re.escape(name) + r'.*successfully loaded', logs), name + ' not loaded'
                return {'actual_lab_html': 'passed', 'page_config_path': browser_path,
                        'served_entry': ENTRY, 'rtc_server_loaded': True,
                        'human_oauth_or_gateway_requests': False}
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    proc.kill(); proc.wait(timeout=5)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--server-probe', action='store_true')
    args = parser.parse_args()
    result = {'versions': packages_and_hook(), 'qualification': 'CPS CPU package candidate only; no hardware or live API calls'}
    if args.execute:
        result['execution'] = hera_and_notebooks()
    if args.server_probe:
        result['server'] = [server_probe(), server_probe('/services/cps-admin/api/compute/v1/')]
    print(json.dumps(result, indent=2, sort_keys=True))
