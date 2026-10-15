"""Inventory base/candidate distribution metadata and inherited Jupyter startup."""
from importlib import metadata
from pathlib import Path
import hashlib,json,os,sys

def inventory():
    files={}
    for dist in metadata.distributions():
        name=dist.metadata['Name'].lower().replace('_','-')
        if name.startswith('cps-compute'):continue
        for item in dist.files or ():
            if '.dist-info/' in str(item) and item.name in {'METADATA','RECORD','entry_points.txt'}:
                path=dist.locate_file(item)
                if path.is_file():files[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
    for root in ['/etc/jupyter','/usr/local/etc/jupyter',str(Path(sys.prefix)/'etc/jupyter'),'/usr/local/bin']:
        for path in Path(root).rglob('*'):
            if path.is_file() and (root!='/usr/local/bin' or path.name in {'start.sh','start-notebook.py','start-singleuser.py'}):
                files[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
    return {'python':sys.version.split()[0],'uid':os.getuid(),'gid':os.getgid(),'cwd':os.getcwd(),
            'versions':{d.metadata['Name'].lower().replace('_','-'):d.version for d in metadata.distributions()},
            'inherited_files':files}

if __name__=='__main__':print(json.dumps(inventory(),sort_keys=True,indent=2))
