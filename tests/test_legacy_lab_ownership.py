"""Filesystem-only regression fixtures for explicit legacy Lab ownership retirement."""
import base64
import csv
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from release.legacy_lab_ownership import transfer


def digest(data):
    return hashlib.sha256(data).hexdigest()


def row(path, data):
    encoded = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b'=').decode()
    stream = io.StringIO(newline='')
    csv.writer(stream, lineterminator='\r\n').writerow([path, 'sha256=' + encoded, len(data)])
    return stream.getvalue().encode()


class LegacyLabOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.prefix = Path(self.temp.name).resolve()
        self.site = self.prefix / 'lib/python3.12/site-packages'
        self.dist = self.site / 'cps_compute-0.1.0.dist-info'
        self.dist.mkdir(parents=True)
        self.metadata = self.dist / 'METADATA'
        self.metadata.write_bytes(b'Metadata-Version: 2.1\nName: cps-compute\nVersion: 0.1.0\n')
        self.record = self.dist / 'RECORD'
        self.namespace = self.prefix / 'share/jupyter/labextensions/@cps/compute-jupyterlab'
        self.asset = self.namespace / 'static/obsolete.js'
        self.asset.parent.mkdir(parents=True)
        self.asset.write_bytes(b'old lab bundle\n')
        self.sdk = self.site / 'cps_compute/__init__.py'
        self.sdk.parent.mkdir()
        self.sdk.write_bytes(b'answer = 42\n')
        self.asset_record = '../../../share/jupyter/labextensions/@cps/compute-jupyterlab/static/obsolete.js'
        self.retired_row = row(self.asset_record, self.asset.read_bytes())
        self.kept = (row('cps_compute/__init__.py', self.sdk.read_bytes())
                     + row('cps_compute-0.1.0.dist-info/METADATA', self.metadata.read_bytes())
                     + b'"cps_compute-0.1.0.dist-info/RECORD",,\r\n')
        self.record.write_bytes(self.kept + self.retired_row)

    def run_transfer(self, **kwargs):
        pins = dict(metadata_sha256=digest(self.metadata.read_bytes()),
                    record_sha256=digest(self.record.read_bytes()), execute=True)
        pins.update(kwargs)
        return transfer(self.prefix, self.dist, **pins)

    def snapshot(self):
        return {str(p.relative_to(self.prefix)): p.read_bytes()
                for p in self.prefix.rglob('*') if p.is_file()}

    def assert_denied(self, **kwargs):
        before = self.snapshot()
        with self.assertRaises((ValueError, RuntimeError, OSError)):
            self.run_transfer(**kwargs)
        self.assertEqual(before, self.snapshot())

    def test_inert_default_does_not_read(self):
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('read')), \
             patch.object(Path, 'open', side_effect=AssertionError('open')), \
             patch.object(Path, 'resolve', side_effect=AssertionError('resolve')):
            result = transfer(Path('/absent'), Path('/absent/dist'),
                              metadata_sha256='0' * 64, record_sha256='0' * 64)
        self.assertFalse(result['changed'])

    def test_transfer_preserves_every_kept_byte_and_reports_hashes(self):
        before = self.record.read_bytes()
        sdk, metadata = self.sdk.read_bytes(), self.metadata.read_bytes()
        asset = self.asset.read_bytes()
        result = self.run_transfer()
        self.assertFalse(self.asset.exists())
        self.assertEqual(self.kept, self.record.read_bytes())
        self.assertEqual(sdk, self.sdk.read_bytes())
        self.assertEqual(metadata, self.metadata.read_bytes())
        self.assertTrue(result['changed'])
        self.assertEqual(digest(before), result['previous_record_sha256'])
        self.assertEqual(digest(self.kept), result['new_record_sha256'])
        self.assertEqual([dict(prefix_path=str(self.asset.relative_to(self.prefix)),
                               record_path=self.asset_record, sha256=digest(asset),
                               bytes=len(asset))], result['retired'])

    def test_noncanonical_or_relative_prefix_denies(self):
        original = self.prefix
        for prefix in (Path('.'), original / 'lib/..'):
            with self.subTest(prefix=prefix):
                self.prefix = prefix
                try:
                    with self.assertRaises((ValueError, RuntimeError, OSError)):
                        self.run_transfer()
                finally:
                    self.prefix = original
        self.assertTrue(self.asset.exists())

    def test_wrong_metadata_identity_denies(self):
        self.metadata.write_bytes(b'Name: unrelated-package\nVersion: 0.1.0\n')
        self.assert_denied()

    def test_wrong_dist_info_location_denies(self):
        original = self.dist
        moved = self.site / 'cps_compute-9.9.dist-info'
        original.rename(moved)
        self.dist = moved
        self.metadata = moved / 'METADATA'
        self.record = moved / 'RECORD'
        self.assert_denied()

    def test_bad_asset_hash_denies_before_mutation(self):
        self.asset.write_bytes(b'tampered bundle\n')
        self.assert_denied()

    def test_bad_asset_size_denies_before_mutation(self):
        self.record.write_bytes(self.kept + self.retired_row.replace(b',15\r\n', b',999\r\n'))
        self.assert_denied()

    def test_bad_pins_deny_before_mutation(self):
        for pin in ('metadata_sha256', 'record_sha256'):
            with self.subTest(pin=pin):
                self.assert_denied(**{pin: '0' * 64})

    def test_absolute_and_traversal_alias_rows_deny(self):
        aliases = [str(self.asset), self.asset_record.replace('/static/', '/static/../static/')]
        for alias in aliases:
            with self.subTest(alias=alias):
                self.record.write_bytes(self.kept + row(alias, self.asset.read_bytes()))
                self.assert_denied()

    def test_symlink_asset_denies(self):
        target = self.prefix / 'target.js'
        target.write_bytes(self.asset.read_bytes())
        self.asset.unlink()
        self.asset.symlink_to(target)
        self.assert_denied()

    def test_symlink_ancestor_denies(self):
        target = self.prefix / 'actual-static'
        self.asset.parent.rename(target)
        self.asset.parent.symlink_to(target, target_is_directory=True)
        self.assert_denied()

    def test_other_distribution_owning_namespace_denies(self):
        other = self.site / 'other-1.0.dist-info'
        other.mkdir()
        (other / 'RECORD').write_bytes(row(self.asset_record, self.asset.read_bytes()))
        self.assert_denied()

    def test_unknown_namespace_file_denies(self):
        (self.namespace / 'unknown.js').write_bytes(b'unknown')
        self.assert_denied()

    def test_modular_sdk_is_noop_with_separately_owned_addon(self):
        self.record.write_bytes(self.kept)
        other = self.site / 'cps_compute_jupyterlab-0.1.0.dist-info'
        other.mkdir()
        (other / 'RECORD').write_bytes(row(self.asset_record, self.asset.read_bytes()))
        before = self.snapshot()
        result = self.run_transfer()
        self.assertFalse(result['changed'])
        self.assertEqual([], result['retired'])
        self.assertEqual(before, self.snapshot())


if __name__ == '__main__':
    unittest.main()
