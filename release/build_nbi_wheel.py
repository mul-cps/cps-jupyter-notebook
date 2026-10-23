#!/usr/bin/env python3
"""Build the pinned NBI startup patch, preserving upstream wheel ownership."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

UPSTREAM_SHA256 = '22466fe295e1c36fca2c4f4932f71f48532df44c45b2cfe154834d1312a84c82'
SOURCE_SHA256 = 'ff04462b39a89b6f0ec4fe3cad161dd3c13798f105f07c223ab0bdd1d4dfabd2'
VERSION = '4.6.0+cps.1'


def build(wheel, output):
    wheel = Path(wheel).resolve()
    if hashlib.sha256(wheel.read_bytes()).hexdigest() != UPSTREAM_SHA256:
        raise ValueError('Unreviewed upstream wheel')
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        subprocess.run([sys.executable, '-m', 'wheel', 'unpack', str(wheel),
                        '--dest', temporary], check=True)
        root = Path(temporary) / 'notebook_intelligence-4.6.0'
        source = root / 'notebook_intelligence/claude.py'
        raw = source.read_bytes()
        if hashlib.sha256(raw).hexdigest() != SOURCE_SHA256:
            raise ValueError('Unreviewed Claude client source')
        before = b'        self._continue_conversation: bool | None = None\n        self.connect()\n'
        if raw.count(before) != 1:
            raise ValueError('Unexpected constructor')
        source.write_bytes(raw.replace(before, b'        self._continue_conversation: bool | None = None\n'))
        version = root / 'notebook_intelligence/_version.py'
        version.write_bytes(version.read_bytes().replace(b"'4.6.0'", repr(VERSION).encode()))
        info = root / 'notebook_intelligence-4.6.0.dist-info'
        metadata = info / 'METADATA'
        raw = metadata.read_bytes()
        if raw.count(b'Version: 4.6.0\n') != 1:
            raise ValueError('Unexpected upstream version metadata')
        # Upstream imports MCP 1.x APIs; FastMCP 4.x targets the newer API.
        raw = raw.replace(b'Version: 4.6.0\n', f'Version: {VERSION}\n'.encode())
        header, body = raw.split(b'\n\n', 1)
        raw = header + b'\nRequires-Dist: mcp<2\nRequires-Dist: fastmcp<3\n\n' + body
        metadata.write_bytes(raw)
        (info / 'cps-patch.json').write_text(json.dumps({
            'upstream_version': '4.6.0', 'upstream_sha256': UPSTREAM_SHA256,
            'version': VERSION,
            'changes': ['Connect Claude on first use, not client construction',
                        'Constrain dependencies to imported MCP/FastMCP APIs'],
        }, sort_keys=True, indent=2) + '\n')
        info.rename(root / f'notebook_intelligence-{VERSION}.dist-info')
        data = root / 'notebook_intelligence-4.6.0.data'
        if data.exists():
            data.rename(root / f'notebook_intelligence-{VERSION}.data')
        env = dict(os.environ, SOURCE_DATE_EPOCH='1767225600')
        subprocess.run([sys.executable, '-m', 'wheel', 'pack', str(root),
                        '--dest-dir', str(output)], check=True, env=env)
    return output / f'notebook_intelligence-{VERSION}-py3-none-any.whl'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('upstream_wheel')
    parser.add_argument('output_directory')
    args = parser.parse_args()
    print(build(args.upstream_wheel, args.output_directory))
