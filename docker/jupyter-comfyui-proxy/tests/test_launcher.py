"""Exercise the launcher against a fake app, without starting ComfyUI/GPU work."""
import json
from importlib import metadata
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'src'


class LauncherTests(unittest.TestCase):
    def launch(self, root, data_dir=None, extra=(), exit_code=0):
        app = root / 'app with spaces'
        app.mkdir()
        (app / 'main.py').write_text(
            'import json, os, sys\n'
            'print(json.dumps({"argv":sys.argv,"cwd":os.getcwd(),'
            '"marker":os.environ["LAUNCHER_TEST_MARKER"]}))\n'
            'sys.exit(int(os.environ["LAUNCHER_TEST_EXIT"]))\n'
        )
        home = root / 'home'
        home.mkdir()
        env = dict(os.environ, PYTHONPATH=str(SOURCE), COMFYUI_PATH=str(app),
                   HOME=str(home), LAUNCHER_TEST_MARKER='preserved',
                   LAUNCHER_TEST_EXIT=str(exit_code))
        env.pop('COMFYUI_DATA_DIR', None)
        launcher = os.environ.get('COMFYUI_TEST_LAUNCHER')
        if launcher:
            env.pop('PYTHONPATH', None)
        if data_dir is not None:
            env['COMFYUI_DATA_DIR'] = data_dir
        result = subprocess.run(
            ([launcher, *extra] if launcher else
             [sys.executable, '-m', 'jupyter_comfyui_proxy.launcher', *extra]),
            cwd=root, env=env, capture_output=True, text=True, check=True,
        )
        return json.loads(result.stdout.splitlines()[-1]), app, home

    @unittest.skipUnless(os.environ.get('COMFYUI_TEST_LAUNCHER'), 'requires installed wheel')
    def test_installed_entry_points_and_icon(self):
        distribution = metadata.distribution('jupyter-comfyui-proxy')
        entries = { (entry.group, entry.name): entry for entry in distribution.entry_points }
        launcher = entries[('console_scripts', 'jupyter-comfyui-launcher')]
        self.assertTrue(callable(launcher.load()))
        config = entries[('jupyter_serverproxy_servers', 'comfyui')].load()()
        self.assertEqual(config['command'], ['jupyter-comfyui-launcher'])
        self.assertEqual(config['port'], 8188)
        self.assertTrue(Path(config['launcher_entry']['icon_path']).is_file())

    def test_default_persistent_paths_and_forwarded_arguments(self):
        with tempfile.TemporaryDirectory() as directory:
            result, app, home = self.launch(Path(directory), extra=('--cpu', '--name', 'a b'))
            data = home / '.local/share/comfyui'
            self.assertEqual(result['cwd'], str(app))
            self.assertEqual(result['marker'], 'preserved')
            self.assertEqual(result['argv'], [
                'main.py', '--listen', '127.0.0.1', '--port', '8188',
                '--input-directory', str(data / 'input'),
                '--output-directory', str(data / 'output'),
                '--temp-directory', str(data / 'temp'),
                '--user-directory', str(data / 'user'),
                '--database-url', 'sqlite:///' + str(data / 'user/comfyui.db'),
                '--cpu', '--name', 'a b',
            ])
            for name in ('input', 'output', 'temp', 'user'):
                self.assertTrue((data / name).is_dir())

    def test_relative_override_is_resolved_from_app_like_original_shell(self):
        with tempfile.TemporaryDirectory() as directory:
            result, app, _ = self.launch(Path(directory), data_dir='state with spaces')
            self.assertIn(str(app / 'state with spaces/input'), result['argv'])

    def test_symlink_override_preserves_configured_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / 'persistent'
            target.mkdir()
            link = root / 'state-link'
            link.symlink_to(target, target_is_directory=True)
            result, _, _ = self.launch(root, data_dir=str(link))
            self.assertIn(str(link / 'input'), result['argv'])
            self.assertTrue((target / 'input').is_dir())

    def test_child_failure_exit_code_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(subprocess.CalledProcessError) as failure:
                self.launch(Path(directory), exit_code=23)
            self.assertEqual(failure.exception.returncode, 23)

    def test_empty_override_falls_back_to_home(self):
        with tempfile.TemporaryDirectory() as directory:
            result, _, home = self.launch(Path(directory), data_dir='')
            self.assertIn(str(home / '.local/share/comfyui/input'), result['argv'])


if __name__ == '__main__':
    unittest.main()
