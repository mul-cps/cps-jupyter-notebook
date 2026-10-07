#!/usr/bin/env python3
"""Offline, immutable notebook release overlays. No publishing or GPU execution."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import tarfile
import zipfile
from email.parser import Parser

ROOT = Path(__file__).resolve().parents[1]

def file_sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(1024 * 1024): digest.update(chunk)
    return digest.hexdigest()

def verify_standalone_sbom(archive_path, native_path, spdx_path):
    with tarfile.open(archive_path) as archive:
        def document(name):
            member = archive.getmember(name)
            if not member.isfile() or member.size > 2 * 1024 * 1024:
                raise ValueError('invalid OCI metadata')
            return json.load(archive.extractfile(member))
        def blob(digest):
            if not re.fullmatch(r'sha256:[a-f0-9]{64}', digest):
                raise ValueError('invalid OCI image digest')
            return document('blobs/sha256/' + digest.split(':')[1])
        manifests = document('index.json')['manifests']
        if len(manifests) == 1 and 'index' in manifests[0].get('mediaType', ''):
            manifests = blob(manifests[0]['digest'])['manifests']
        images = [m for m in manifests if m.get('platform', {}).get('architecture') == 'amd64']
        if len(images) != 1: raise ValueError('one amd64 OCI image required')
        image = images[0]
        config_digest = blob(image['digest'])['config']['digest']
    native = json.loads(native_path.read_text())
    metadata = native['source']['metadata']
    if metadata.get('imageID') != config_digest or metadata.get('manifestDigest') != image['digest']:
        raise ValueError('SBOM source differs from OCI image')
    spdx = json.loads(spdx_path.read_text())
    if not spdx.get('spdxVersion', '').startswith('SPDX-2.'):
        raise ValueError('SPDX 2 document required')
    packages = {(p['name'], p.get('versionInfo', '')) for p in spdx.get('packages', [])}
    expected = {(p['name'], p.get('version', '')) for p in native.get('artifacts', [])}
    if not expected or not expected <= packages or not any(name.replace('_', '-') == 'cps-compute' for name, _ in packages):
        raise ValueError('SBOM package inventory missing or inconsistent')
    return {'format': 'standalone SPDX JSON', 'file': spdx_path.name,
            'sourceImageId': config_digest, 'packages': len(spdx['packages']),
            'sha256': file_sha256(spdx_path), 'nativeFile': native_path.name,
            'nativeSha256': file_sha256(native_path)}

def generate_standalone_sbom(archive, syft, checksum):
    if not re.fullmatch(r'[a-f0-9]{64}', checksum or '') or file_sha256(syft) != checksum:
        raise ValueError('scanner checksum mismatch')
    stem = archive.name.removesuffix('.oci.tar')
    native = archive.with_name(stem + '.sbom.syft.json')
    spdx = archive.with_name(stem + '.sbom.spdx.json')
    with tempfile.TemporaryDirectory(prefix='sbom-scan-', dir=archive.parent) as directory:
        config = Path(directory) / 'syft.yaml'
        config.write_text('{}\n')
        environment = {k: v for k, v in os.environ.items() if not k.startswith('SYFT_')}
        environment.update(TMPDIR=directory, SYFT_SOURCE_IMAGE_MAX_LAYER_SIZE='16GiB')
        subprocess.run([str(syft.resolve()), 'scan', 'oci-archive:' + str(archive.resolve()),
                        '--config', str(config), '--select-catalogers', 'image,file,+sbom-cataloger',
                        '-o', 'syft-json=' + str(native.resolve()),
                        '-o', 'spdx-json=' + str(spdx.resolve())], check=True, env=environment)
    result = verify_standalone_sbom(archive, native, spdx)
    result['scannerSha256'] = checksum
    return result

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
    hashes = {}; packages = {}
    for filename, digest in lock['wheelFiles'].items():
        if Path(filename).name != filename or not filename.endswith('.whl'): raise ValueError('unsafe wheel filename')
        path = wheelhouse / filename
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest: raise ValueError('wheel checksum mismatch')
        with zipfile.ZipFile(path) as archive:
            meta = [n for n in archive.namelist() if n.count('/') == 1 and n.endswith('.dist-info/METADATA')]
            if len(meta) != 1: raise ValueError('invalid wheel metadata')
            data = Parser().parsestr(archive.read(meta[0]).decode())
            name = re.sub(r'[-_.]+', '-', data['Name'].lower()); version = data['Version']
            if name in packages and packages[name] != version:
                raise ValueError('conflicting wheel package versions')
            packages[name] = version
            if name == 'cps-compute' and not any('labextensions/@cps/compute-jupyterlab/package.json' in n for n in archive.namelist()):
                raise ValueError('compute wheel must include the prebuilt addon')
            hashes.setdefault(name, set()).add(digest)
    if packages.get('cps-compute') != lock['computeVersion'].replace('-rc.', 'rc'):
        raise ValueError('compute wheel version must match release target')
    if 'jupyter-collaboration' not in packages: raise ValueError('pinned RTC wheel required')
    return [f'{name}=={packages[name]} ' + ' '.join('--hash=sha256:'+digest for digest in sorted(hashes[name]))
            for name in sorted(packages)]

def build_command(lock, variant, revision, context, output, buildctl_address=None, *, standalone_sbom=False):
    labels = {'org.opencontainers.image.version': lock['release'],
              'org.opencontainers.image.revision': revision,
              'compute.cps.unileoben.ac.at/policy-hash': lock['policyHash']}
    metadata = str(output / (variant + '.metadata.json'))
    destination = 'type=oci,dest=' + str(output / (variant + '.oci.tar'))
    if buildctl_address:
        command = ['buildctl', '--addr', buildctl_address, 'build',
                   '--frontend', 'dockerfile.v0', '--local', 'context=' + str(context),
                   '--local', 'dockerfile=' + str(context), '--opt', 'platform=linux/amd64',
                   '--opt', 'force-network-mode=none',
                   '--opt', 'attest:provenance=mode=max', '--opt',
                   'build-arg:BASE_IMAGE=' + lock['baseDigests'][variant]]
        if not standalone_sbom: command.extend(['--opt', 'attest:sbom='])
        for name, value in labels.items(): command.extend(['--opt', 'label:' + name + '=' + value])
    else:
        command = ['docker', 'buildx', 'build', '--network=none', '--platform=linux/amd64',
                   '--sbom=false' if standalone_sbom else '--sbom=true', '--provenance=mode=max', '--build-arg',
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
    parser.add_argument('--standalone-sbom', action='store_true', help='Produce full SPDX files outside the embedded attestation size limit')
    parser.add_argument('--syft', type=Path, help='Reviewed standalone Syft executable')
    parser.add_argument('--syft-sha256', help='Reviewed SHA-256 of the Syft executable')
    args=parser.parse_args(); lock=json.loads(args.lock.read_text())
    if args.standalone_sbom and (not args.syft or not re.fullmatch(r'[a-f0-9]{64}', args.syft_sha256 or '') or file_sha256(args.syft) != args.syft_sha256):
        parser.error('standalone SBOM requires a scanner with its reviewed checksum')
    requirements=validate(lock,args.wheelhouse)
    revision=subprocess.check_output(['git','rev-parse',lock['sourceTag']+'^{commit}'],cwd=ROOT,text=True).strip()
    if revision != subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(): raise ValueError('build checkout must match source tag')
    if subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip(): raise ValueError('release checkout must be clean')
    if not args.build:
        print(json.dumps({'validated':True,'revision':revision,'variants':lock['variants']},indent=2)); return
    args.output.mkdir(parents=True,exist_ok=False)
    sboms = {}
    with tempfile.TemporaryDirectory(prefix='cps-notebook-release-') as directory:
        context=Path(directory); wheels=context/'release-wheelhouse'; wheels.mkdir()
        for filename in lock['wheelFiles']: shutil.copyfile(args.wheelhouse/filename,wheels/filename)
        (wheels/'requirements.txt').write_text('\n'.join(requirements)+'\n')
        shutil.copyfile(ROOT/'docker/Dockerfile.compute-runtime',context/'Dockerfile')
        for variant in lock['variants']:
            subprocess.run(build_command(lock,variant,revision,context,args.output,args.buildctl_address,standalone_sbom=args.standalone_sbom),check=True)
            if args.standalone_sbom:
                sboms[variant] = generate_standalone_sbom(args.output/(variant+'.oci.tar'), args.syft, args.syft_sha256)
    inventory={**lock,'sourceRevision':revision,'images':{}}
    for variant in lock['variants']:
        metadata=json.loads((args.output/(variant+'.metadata.json')).read_text())
        digest=metadata.get('containerimage.digest')
        if not digest or not re.fullmatch(r'sha256:[a-f0-9]{64}',digest): raise ValueError('builder produced no immutable image digest')
        inventory['images'][variant]={'digest':digest,'oci':variant+'.oci.tar','sbom':sboms.get(variant, 'embedded OCI attestation'),'qualification':'not-run'}
    (args.output/'release.json').write_text(json.dumps(inventory,indent=2)+'\n')
    paths=sorted(p for p in args.output.iterdir() if p.is_file())
    (args.output/'SHA256SUMS').write_text(''.join(file_sha256(p)+'  '+p.name+'\n' for p in paths))

if __name__ == '__main__': main()
