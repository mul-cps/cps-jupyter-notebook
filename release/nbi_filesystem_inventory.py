#!/usr/bin/env python3
"""Inventory an image rootfs without executing its Python or following symlinks.

The CLI requires an exact read-only containerd overlay mount. Output is evidence,
not a software-preservation verdict or hardware qualification.
"""
import argparse
import base64
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys


def require_readonly_mount(root, mountinfo):
    root=Path(root).absolute()
    def decode(value):return re.sub(r'\\([0-7]{3})', lambda m:chr(int(m[1],8)),value)
    matches=[]
    for line in mountinfo.splitlines():
        fields=line.split()
        if len(fields)<10 or '-' not in fields:continue
        separator=fields.index('-')
        mounted=Path(decode(fields[4]))
        if mounted!=root and mounted.is_relative_to(root):raise ValueError('Nested mounts are forbidden in image evidence')
        if mounted==root:matches.append((fields,separator))
    if root==Path('/') or len(matches)!=1:raise ValueError('Exact dedicated image mount required')
    fields,separator=matches[0]
    if 'ro' not in fields[5].split(',') or 'rw' in fields[5].split(',') or fields[separator+1]!='overlay':
        raise ValueError('Read-only overlay image mount required')


def inventory(root, progress=None):
    root=Path(root).absolute()
    if not stat.S_ISDIR(root.lstat().st_mode):raise ValueError('Real root directory required')
    entries={};links={};hashed={};directories_seen={}
    def identity(value):
        return tuple(getattr(value,k) for k in ('st_dev','st_ino','st_mode','st_uid','st_gid','st_size','st_mtime_ns','st_ctime_ns','st_nlink','st_rdev'))
    kinds=((stat.S_ISREG,'file'),(stat.S_ISDIR,'directory'),(stat.S_ISLNK,'symlink'),
           (stat.S_ISFIFO,'fifo'),(stat.S_ISCHR,'character-device'),(stat.S_ISBLK,'block-device'),
           (stat.S_ISSOCK,'socket'))
    def visit(p):
        logical='/' if p==root else '/'+p.relative_to(root).as_posix()
        before=p.lstat()
        kind=next((name for predicate,name in kinds if predicate(before.st_mode)),None)
        if kind is None:raise ValueError('Unknown filesystem entry kind')
        digest=None;size=0;target=None
        if kind=='symlink':
            target=os.readlink(p);raw=os.fsencode(target);size=len(raw);digest=hashlib.sha256(raw).hexdigest()
        elif kind=='file':
            key=(before.st_dev,before.st_ino)
            size=before.st_size
            fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
            try:
                if identity(os.fstat(fd))!=identity(before):raise ValueError('Opened image inode differs')
                if key in hashed:
                    signature,digest=hashed[key]
                    if signature!=identity(before):raise ValueError('Hardlinked image entry changed')
                else:
                    h=hashlib.sha256()
                    with os.fdopen(fd,'rb',closefd=False) as stream:
                        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
                    digest=h.hexdigest()
                xattrs={name:base64.b64encode(os.getxattr(fd,name)).decode()
                        for name in sorted(os.listxattr(fd)) if not name.startswith('trusted.overlay.')}
                if identity(os.fstat(fd))!=identity(before):raise ValueError('Opened image entry changed during inventory')
                hashed[key]=(identity(before),digest)
            finally:os.close(fd)
        if kind!='file':
            xattrs={name:base64.b64encode(os.getxattr(p,name,follow_symlinks=False)).decode()
                    for name in sorted(os.listxattr(p,follow_symlinks=False))
                    if not name.startswith('trusted.overlay.')}
        if kind!='directory' and before.st_nlink>1:links.setdefault((before.st_dev,before.st_ino),[]).append(logical)
        if kind=='directory':directories_seen[p]=identity(before)
        after=p.lstat()
        if identity(before)!=identity(after):raise ValueError('Image entry changed during inventory')
        entries[logical]={'kind':kind,'sha256':digest,'bytes':size,'mode':stat.S_IMODE(before.st_mode),
                          'uid':before.st_uid,'gid':before.st_gid,'target':target,
                          'rdev':before.st_rdev if kind in ('character-device','block-device') else None,
                          'xattrs':xattrs}
        if progress is not None and len(entries)%10000==0:progress(len(entries))
    def error(exc):raise exc
    visit(root)
    for parent,directories,files in os.walk(root,followlinks=False,onerror=error):
        for name in sorted(directories+files):visit(Path(parent)/name)
    if any(identity(p.lstat())!=value for p,value in directories_seen.items()):raise ValueError('Image directory changed during traversal')
    return {'schema':'cps-image-filesystem-inventory/v1','entries':entries,
            'hardlinks':sorted(sorted(paths) for paths in links.values() if len(paths)>1),
            'excluded_storage_xattr_prefixes':['trusted.overlay.']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--image',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if not re.fullmatch(r'[^\s]+@sha256:[a-f0-9]{64}',args.image):raise ValueError('Immutable image reference required')
    root=args.root.absolute()
    require_readonly_mount(root,Path('/proc/self/mountinfo').read_text())
    if args.output.absolute().is_relative_to(root):raise ValueError('Evidence output cannot be inside the image')
    result=inventory(root,lambda count:print(json.dumps({'entries_scanned':count}),file=sys.stderr,flush=True))
    result['image']=args.image
    result['inventory_source_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    raw=json.dumps(result,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
    # A zero timestamp makes the compressed evidence reproducible.
    args.output.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    with args.output.open('wb') as stream:
        with gzip.GzipFile(filename='',mode='wb',fileobj=stream,mtime=0,compresslevel=3) as compressed:compressed.write(raw)
    args.output.chmod(0o600)
    print(json.dumps({'image':args.image,'entries':len(result['entries']),
                      'raw_bytes':len(raw),'raw_sha256':hashlib.sha256(raw).hexdigest(),
                      'hardware_qualified':False}),flush=True)


if __name__=='__main__':main()
