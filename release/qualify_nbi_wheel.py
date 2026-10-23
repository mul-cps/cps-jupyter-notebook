#!/usr/bin/env python3
"""Opt-in artifact checks against the exact reviewed upstream wheel."""
import argparse
from email.parser import BytesParser
import hashlib
from pathlib import Path
import tempfile
import zipfile

from build_nbi_wheel import build, VERSION


def payload(path):
    with zipfile.ZipFile(path) as archive:
        return {name.replace(f'-{VERSION}.', '-4.6.0.'): archive.read(name)
                for name in archive.namelist()}


def qualify(upstream):
    before = payload(upstream)
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        first = build(upstream, root / 'first')
        second = build(upstream, root / 'second')
        assert first.read_bytes() == second.read_bytes(), 'Build is not reproducible'
        after = payload(first)
        info = 'notebook_intelligence-4.6.0.dist-info/'
        assert set(after) - set(before) == {info + 'cps-patch.json'}
        assert not set(before) - set(after)
        changed = {name for name in before if before[name] != after[name]}
        assert changed == {'notebook_intelligence/claude.py',
                           'notebook_intelligence/_version.py',
                           info + 'METADATA', info + 'RECORD'}, changed
        meta = BytesParser().parsebytes(after[info + 'METADATA'])
        assert meta['Version'] == VERSION
        assert {'mcp<2', 'fastmcp<3'} <= set(meta.get_all('Requires-Dist'))
        # WheelFile validates every hashed payload when it is read.
        from wheel.wheelfile import WheelFile
        with WheelFile(first) as archive:
            for name in archive.namelist():
                archive.read(name)
        bad = root / 'unreviewed.whl'
        bad.write_bytes(Path(upstream).read_bytes() + b'changed')
        try:
            build(bad, root / 'bad')
        except ValueError as error:
            assert str(error) == 'Unreviewed upstream wheel'
        else:
            raise AssertionError('Unreviewed wheel accepted')
        print('PASS: deterministic build, payload preservation, RECORD integrity, pin rejection')
        print('Patched SHA256:', hashlib.sha256(first.read_bytes()).hexdigest())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('upstream_wheel')
    qualify(parser.parse_args().upstream_wheel)
