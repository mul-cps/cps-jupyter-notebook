#!/usr/bin/env python3
"""Retire pinned legacy SDK-owned Lab assets before installing the modular addon.

Run only in an exclusive, disposable image-build filesystem. No imports of the
installed SDK, pip operations, network calls or SDK uninstall are performed.
"""
import argparse
import base64
import csv
from email.parser import BytesParser
import hashlib
import io
import json
import os
from pathlib import Path
import posixpath
import re
import secrets
import stat
from contextlib import contextmanager

NAMESPACE = Path('share/jupyter/labextensions/@cps/compute-jupyterlab')
LIMIT = 64 * 1024 * 1024
DIRECTORY = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


@contextmanager
def directory(path):
    """Open every directory component without following symlinks."""
    path = Path(path)
    require(path.is_absolute() and str(path) == posixpath.normpath(str(path))
            and not str(path).startswith('//'), 'Canonical absolute directory required')
    fd = os.open('/', DIRECTORY)
    try:
        for part in path.parts[1:]:
            child = os.open(part, DIRECTORY, dir_fd=fd)
            os.close(fd); fd = child
        yield fd
    finally:
        os.close(fd)


def read_at(parent, name):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=parent)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode), 'Regular installed file required')
        raw = stream.read(LIMIT + 1)
        after = os.fstat(stream.fileno())
    require(len(raw) <= LIMIT and stamp(before) == stamp(after), 'Installed file changed during read')
    require(stamp(os.stat(name, dir_fd=parent, follow_symlinks=False)) == stamp(after), 'Installed file identity changed')
    return raw, after


def read(path):
    with directory(path.parent) as parent:
        return read_at(parent, path.name)


def stamp(value):
    return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns,
            value.st_mode, value.st_uid, value.st_gid)


def target(site, prefix, value):
    require(isinstance(value, str) and value and not value.startswith('/')
            and not any(ord(c) < 32 or c == '\\' for c in value), 'Canonical relative RECORD path required')
    result = Path(posixpath.normpath(str(site / value)))
    require(result.is_relative_to(prefix) and value == posixpath.relpath(result, site), 'RECORD escaped prefix or used a path alias')
    return result


def rows(raw, site, prefix):
    text = raw.decode('utf-8')
    lines = text.splitlines(keepends=True)
    reader = csv.reader(io.StringIO(text, newline=''), strict=True)
    result = []; previous = 0; seen = set()
    for row in reader:
        require(len(row) == 3 and reader.line_num == previous + 1, 'Single-line three-column RECORD required')
        path = target(site, prefix, row[0])
        require(path not in seen, 'Duplicate installed RECORD path')
        seen.add(path)
        result.append((row, lines[previous].encode('utf-8'), path))
        previous = reader.line_num
    require(result, 'Installed RECORD required')
    return result


def inventory(root):
    files = set()
    with directory(root) as fd, os.scandir(fd) as entries:
        for entry in entries:
            mode = entry.stat(follow_symlinks=False).st_mode
            require(not stat.S_ISLNK(mode), 'Symlink in Lab namespace')
            path = root / entry.name
            if stat.S_ISDIR(mode):
                files.update(inventory(path))
            else:
                require(stat.S_ISREG(mode), 'Regular Lab asset required')
                files.add(path)
    return files


def other_owners(site, prefix, sdk, namespace):
    with directory(site) as fd, os.scandir(fd) as entries:
        names = sorted(entry.name for entry in entries
                       if entry.name.endswith(('.dist-info', '.egg-info')))
    for name in names:
        if name == sdk.name:
            continue
        require(name.endswith('.dist-info'), 'Unsupported legacy distribution ownership metadata')
        raw, _ = read(site / name / 'RECORD')
        require(not any(path.is_relative_to(namespace) for _, _, path in rows(raw, site, prefix)),
                'Another distribution owns the Lab namespace')


def replace_record(path, old, new, original_stat):
    with directory(path.parent) as parent:
        require(read_at(parent, path.name)[0] == old, 'SDK RECORD changed before retirement')
        temporary = '.RECORD.cps-lab-transfer-' + secrets.token_hex(8)
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                     stat.S_IMODE(original_stat.st_mode), dir_fd=parent)
        try:
            with os.fdopen(fd, 'wb') as stream:
                current = os.fstat(stream.fileno())
                if (current.st_uid, current.st_gid) != (original_stat.st_uid, original_stat.st_gid):
                    os.fchown(stream.fileno(), original_stat.st_uid, original_stat.st_gid)
                os.fchmod(stream.fileno(), stat.S_IMODE(original_stat.st_mode))
                stream.write(new); stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, path.name, src_dir_fd=parent, dst_dir_fd=parent)
        finally:
            try: os.unlink(temporary, dir_fd=parent)
            except FileNotFoundError: pass


def transfer(prefix, sdk_dist_info, *, metadata_sha256, record_sha256, execute=False):
    if not execute:
        return {'inert': True, 'files_changed': False, 'changed': False}
    prefix = Path(prefix); sdk = Path(sdk_dist_info); site = sdk.parent
    require(prefix.is_absolute() and sdk.is_absolute() and sdk.is_relative_to(prefix), 'Explicit installed prefix and SDK required')
    require(re.fullmatch(r'lib(?:64)?/python[0-9]+\.[0-9]+/site-packages', site.relative_to(prefix).as_posix())
            and re.fullmatch(r'cps_compute-[A-Za-z0-9_.+!-]+\.dist-info', sdk.name), 'Exact wheel-installed SDK location required')
    require(all(isinstance(pin, str) and re.fullmatch(r'[a-f0-9]{64}', pin)
                for pin in (metadata_sha256, record_sha256)), 'Explicit raw SHA256 pins required')
    metadata, _ = read(sdk / 'METADATA'); original, original_stat = read(sdk / 'RECORD')
    require(sha(metadata) == metadata_sha256 and sha(original) == record_sha256, 'Pinned SDK METADATA/RECORD changed')
    require(BytesParser().parsebytes(metadata).get_all('Name') == ['cps-compute'], 'Exact cps-compute distribution required')
    parsed = rows(original, site, prefix); namespace = prefix / NAMESPACE
    self_rows = [row for row, _, path in parsed if path == sdk / 'RECORD']
    require(self_rows == [[(sdk / 'RECORD').relative_to(site).as_posix(), '', '']], 'Blank SDK self-RECORD row required')
    retired = [(row, line, path) for row, line, path in parsed if path.is_relative_to(namespace)]
    audit = {'version': 1, 'distribution': 'cps-compute', 'sdk_metadata_sha256': metadata_sha256,
             'previous_record_sha256': record_sha256, 'new_record_sha256': record_sha256,
             'changed': bool(retired), 'retired': []}
    if not retired:
        return audit
    other_owners(site, prefix, sdk, namespace)
    require(inventory(namespace) == {path for _, _, path in retired}, 'Unrecorded asset in legacy Lab namespace')
    checked = []
    for row, _, path in retired:
        require(path != namespace, 'Lab directory cannot be an asset')
        raw, _ = read(path)
        encoded = base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).rstrip(b'=').decode('ascii')
        require(row[1] == 'sha256=' + encoded and row[2] == str(len(raw)), 'Original Lab RECORD hash/size changed')
        checked.append((path, raw))
        audit['retired'].append({'record_path': row[0], 'prefix_path': path.relative_to(prefix).as_posix(),
                                 'sha256': sha(raw), 'bytes': len(raw)})
    audit['retired'].sort(key=lambda item: item['prefix_path'])
    remaining = b''.join(line for _, line, path in parsed if not path.is_relative_to(namespace))
    require(read(sdk / 'METADATA')[0] == metadata and read(sdk / 'RECORD')[0] == original,
            'SDK custody changed before retirement')
    for path, raw in checked:
        with directory(path.parent) as parent:
            require(read_at(parent, path.name)[0] == raw, 'Lab asset changed before retirement')
            os.unlink(path.name, dir_fd=parent)
    replace_record(sdk / 'RECORD', original, remaining, original_stat)
    require(read(sdk / 'METADATA')[0] == metadata and read(sdk / 'RECORD')[0] == remaining,
            'Retired SDK metadata differs')
    audit['new_record_sha256'] = sha(remaining)
    return audit


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    for field in ('prefix', 'sdk-dist-info', 'metadata-sha256', 'record-sha256'):
        parser.add_argument('--' + field)
    args = parser.parse_args(argv)
    if not args.execute:
        print(json.dumps({'inert': True, 'files_changed': False, 'changed': False}, sort_keys=True)); return 0
    try:
        result = transfer(args.prefix, args.sdk_dist_info, metadata_sha256=args.metadata_sha256,
                          record_sha256=args.record_sha256, execute=True)
        print(json.dumps(result, sort_keys=True)); return 0
    except Exception:
        print('Legacy Lab ownership transfer failed; discard this image-build layer', file=__import__('sys').stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
