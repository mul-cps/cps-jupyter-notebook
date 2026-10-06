#!/usr/bin/env python3
"""Offline, immutable notebook release overlays. No publishing or GPU execution."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import zipfile
from email.parser import Parser

ROOT = Path(__file__).resolve().parents[1]

def validate(lock, wheelhouse):
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:-rc\.\d+)?', lock['release']):
        raise ValueError('explicit release version required')
    if lock['sourceTag'] != 'v' + lock['release']:
        raise ValueError('source tag must identify the release')
    if not re.fullmatch(r'sha256:[a-f0-9]{64}', lock.get('policyHash') or ''):
        raise ValueError('reviewed policy hash required')
    required_variants=json.loads((ROOT/'release/variants.json').read_text())
    variants=lock.get('variants')
    if not isinstance(variants,list) or any(not isinstance(v,str) or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*',v) for v in variants):raise ValueError('Unsafe variant identifier')
    if len(set(variants))!=len(variants) or set(variants)!=set(required_variants):raise ValueError('Every committed notebook variant is required exactly once')
    if set(lock['baseDigests']) != set(lock['variants']):
        raise ValueError('every variant requires a reviewed base digest')
    for image in lock['baseDigests'].values():
        if not re.fullmatch(r'[^\s@]+@sha256:[a-f0-9]{64}', image): raise ValueError('immutable base digests required')
    if not lock['wheelFiles']: raise ValueError('released wheelhouse required')
    requirements = []; packages = {}
    for filename, digest in lock['wheelFiles'].items():
        if Path(filename).name != filename or not filename.endswith('.whl'): raise ValueError('unsafe wheel filename')
        path = wheelhouse / filename
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest: raise ValueError('wheel checksum mismatch')
        with zipfile.ZipFile(path) as archive:
            meta = [n for n in archive.namelist() if n.endswith('.dist-info/METADATA')]
            if len(meta) != 1: raise ValueError('invalid wheel metadata')
            data = Parser().parsestr(archive.read(meta[0]).decode())
            name = data['Name'].lower().replace('_','-'); version = data['Version']
            if name in packages: raise ValueError('duplicate wheel package')
            packages[name] = version
            if name == 'cps-compute' and not any('labextensions/@cps/compute-jupyterlab/package.json' in n for n in archive.namelist()):
                raise ValueError('compute wheel must include the prebuilt addon')
            requirements.append(f'{name}=={version} --hash=sha256:{digest}')
    if packages.get('cps-compute') != lock['computeVersion'].replace('-rc.', 'rc'):
        raise ValueError('compute wheel version must match release target')
    if 'jupyter-collaboration' not in packages: raise ValueError('pinned RTC wheel required')
    return sorted(requirements)

def build_command(lock, variant, revision, context, output, buildctl_address=None):
    labels = {'org.opencontainers.image.version': lock['release'],
              'org.opencontainers.image.revision': revision,
              'compute.cps.unileoben.ac.at/policy-hash': lock['policyHash']}
    metadata = str(output / (variant + '.metadata.json'))
    destination = 'type=oci,dest=' + str(output / (variant + '.oci.tar'))
    if buildctl_address:
        command = ['buildctl', '--addr', buildctl_address, 'build',
                   '--frontend', 'dockerfile.v0', '--local', 'context=' + str(context),
                   '--local', 'dockerfile=' + str(context), '--opt', 'platform=linux/amd64',
                   '--opt', 'force-network-mode=none', '--opt', 'attest:sbom=',
                   '--opt', 'attest:provenance=mode=max', '--opt',
                   'build-arg:BASE_IMAGE=' + lock['baseDigests'][variant]]
        for name, value in labels.items(): command.extend(['--opt', 'label:' + name + '=' + value])
    else:
        command = ['docker', 'buildx', 'build', '--network=none', '--platform=linux/amd64',
                   '--sbom=true', '--provenance=mode=max', '--build-arg',
                   'BASE_IMAGE=' + lock['baseDigests'][variant]]
        for name, value in labels.items(): command.extend(['--label', name + '=' + value])
    command.extend(['--metadata-file', metadata, '--output', destination])
    if not buildctl_address: command.append(str(context))
    return command

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lock',type=Path,default=ROOT/'release/targets.json')
    parser.add_argument('--wheelhouse',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--build',action='store_true')
    parser.add_argument('--buildctl-address', help='Use buildctl directly, e.g. podman-container://private-builder')
    args=parser.parse_args(); lock=json.loads(args.lock.read_text())
    requirements=validate(lock,args.wheelhouse)
    revision=subprocess.check_output(['git','rev-parse',lock['sourceTag']+'^{commit}'],cwd=ROOT,text=True).strip()
    if revision != subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(): raise ValueError('build checkout must match source tag')
    if subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip(): raise ValueError('release checkout must be clean')
    if not args.build:
        print(json.dumps({'validated':True,'revision':revision,'variants':lock['variants']},indent=2)); return
    args.output.mkdir(parents=True,exist_ok=False)
    with tempfile.TemporaryDirectory(prefix='cps-notebook-release-') as directory:
        context=Path(directory); wheels=context/'release-wheelhouse'; wheels.mkdir()
        for filename in lock['wheelFiles']: shutil.copyfile(args.wheelhouse/filename,wheels/filename)
        (wheels/'requirements.txt').write_text('\n'.join(requirements)+'\n')
        shutil.copyfile(ROOT/'docker/Dockerfile.compute-runtime',context/'Dockerfile')
        for variant in lock['variants']:
            subprocess.run(build_command(lock,variant,revision,context,args.output,args.buildctl_address),check=True)
    inventory={**lock,'sourceRevision':revision,'images':{}}
    for variant in lock['variants']:
        metadata=json.loads((args.output/(variant+'.metadata.json')).read_text())
        digest=metadata.get('containerimage.digest')
        if not digest or not re.fullmatch(r'sha256:[a-f0-9]{64}',digest): raise ValueError('builder produced no immutable image digest')
        inventory['images'][variant]={'digest':digest,'oci':variant+'.oci.tar','sbom':'embedded OCI attestation','qualification':'not-run'}
    (args.output/'release.json').write_text(json.dumps(inventory,indent=2)+'\n')
    paths=sorted(p for p in args.output.iterdir() if p.is_file())
    (args.output/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in paths))

if __name__ == '__main__': main()
