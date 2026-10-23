import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1]


def module():
    spec = importlib.util.spec_from_file_location('nbi_inventory', HERE/'release/nbi_filesystem_inventory.py')
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


class InventoryTests(unittest.TestCase):
    def test_files_links_and_special_entries_are_read_without_following_links(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary);(root/'data').mkdir()
            (root/'data/value').write_bytes(b'payload')
            os.link(root/'data/value', root/'linked')
            (root/'outside').symlink_to('/etc', target_is_directory=True)
            os.mkfifo(root/'pipe')
            value = module().inventory(root)
            self.assertEqual(value['entries']['/data/value']['bytes'], 7)
            self.assertEqual(value['entries']['/outside']['kind'], 'symlink')
            self.assertEqual(value['entries']['/outside']['target'], '/etc')
            self.assertEqual(value['entries']['/pipe']['kind'], 'fifo')
            self.assertFalse(any(p.startswith('/outside/') for p in value['entries']))
            self.assertEqual(value['hardlinks'], [['/data/value', '/linked']])
            self.assertEqual((root/'data/value').read_bytes(), b'payload')

    def test_security_metadata_and_extended_attributes_are_part_of_inventory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary);p=root/'value';p.write_bytes(b'payload');p.chmod(0o640)
            try:os.setxattr(p, 'user.cps_test', b'exact')
            except OSError:self.skipTest('Filesystem has no user xattrs')
            item=module().inventory(root)['entries']['/value']
            self.assertEqual(item['mode'], 0o640)
            self.assertEqual(item['uid'], p.stat().st_uid)
            self.assertIn('user.cps_test', item['xattrs'])

    def test_mount_check_requires_exact_readonly_overlay_mount(self):
        with tempfile.TemporaryDirectory(prefix='nbi mount ') as temporary:
            root=Path(temporary);escaped=str(root).replace(' ', r'\040')
            line=f'1 0 0:42 / {escaped} ro,relatime - overlay overlay ro,lowerdir=/lower\n'
            module().require_readonly_mount(root, line)
            for bad in (line.replace('ro,relatime','rw,relatime'),line.replace(' - overlay ', ' - ext4 '), ''):
                with self.subTest(mount=bad), self.assertRaises(ValueError):
                    module().require_readonly_mount(root,bad)
            with self.assertRaises(ValueError):module().require_readonly_mount(root/'child',line)


    def test_nested_mounts_are_rejected_even_when_the_root_is_readonly(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            outer=f'1 0 0:42 / {root} ro - overlay overlay ro,lowerdir=/lower\n'
            child=f'2 1 0:43 / {root}/child rw - tmpfs tmpfs rw\n'
            with self.assertRaises(ValueError):module().require_readonly_mount(root,outer+child)

    def test_hardlinked_symlinks_and_fifos_keep_their_topology(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'symlink-a').symlink_to('/outside')
            os.link(root/'symlink-a',root/'symlink-b',follow_symlinks=False)
            os.mkfifo(root/'fifo-a');os.link(root/'fifo-a',root/'fifo-b')
            self.assertEqual(module().inventory(root)['hardlinks'],
                             [['/fifo-a','/fifo-b'],['/symlink-a','/symlink-b']])

    def test_hashed_descriptor_must_match_the_inspected_inode(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);a=root/'a';b=root/'b'
            a.write_bytes(b'original');b.write_bytes(b'replaced')
            m=module();original=os.open
            def substitute(path,flags,*args,**kwargs):
                return original(b if Path(path)==a else path,flags,*args,**kwargs)
            with patch.object(m.os,'open',substitute), self.assertRaises(ValueError):m.inventory(root)

    def test_modified_hardlink_alias_cannot_reuse_stale_cached_digest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);a=root/'a';b=root/'b';a.write_bytes(b'original');os.link(a,b)
            m=module();original=Path.lstat;changed=False
            def change(path):
                nonlocal changed
                if path==b and not changed:
                    changed=True;a.write_bytes(b'changed!')
                return original(path)
            with patch.object(Path,'lstat',change), self.assertRaises(ValueError):m.inventory(root)
