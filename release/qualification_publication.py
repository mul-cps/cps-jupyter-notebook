#!/usr/bin/env python3
"""Publish already tested OCI bytes under closed qualification tags only."""
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

REPOSITORIES = {'ghcr.io/mul-cps/cps-compute', 'ghcr.io/mul-cps/e2x-course-hub',
                'ghcr.io/mul-cps/cps-jupyter-notebook'}


def digest(data):
    return 'sha256:' + hashlib.sha256(data).hexdigest()


def validate_record(record):
    required = {'name', 'source_revision', 'recipe_revision', 'local', 'manifest_digest',
                'config_digest', 'destination'}
    if not isinstance(record, dict) or set(record) != required:
        raise ValueError('Closed qualification publication record required')
    if any(not isinstance(record[key], str) for key in required):
        raise ValueError('String publication fields required')
    if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', record['name']):
        raise ValueError('Safe artifact name required')
    for key in ('source_revision', 'recipe_revision'):
        if not re.fullmatch(r'[0-9a-f]{40}', record[key]):
            raise ValueError('Full source SHA required')
    for key in ('manifest_digest', 'config_digest'):
        if not re.fullmatch(r'sha256:[0-9a-f]{64}', record[key]):
            raise ValueError('Full OCI digest required')
    repository, separator, tag = record['destination'].partition(':')
    if (separator != ':' or repository not in REPOSITORIES
            or not re.fullmatch(r'[a-z0-9-]*qualification-[a-z0-9-]+', tag)
            or record['source_revision'][:8] not in tag):
        raise ValueError('Existing mul-cps repository and source-bound qualification tag required')


def verify_bytes(record, manifest_raw, config_raw):
    validate_record(record)
    if digest(manifest_raw) != record['manifest_digest'] or digest(config_raw) != record['config_digest']:
        raise ValueError('Published bytes differ from the tested immutable OCI artifact')
    manifest, config = json.loads(manifest_raw), json.loads(config_raw)
    if (manifest.get('schemaVersion') != 2
            or manifest.get('mediaType') != 'application/vnd.oci.image.manifest.v1+json'
            or manifest.get('config', {}).get('digest') != record['config_digest']
            or not isinstance(manifest.get('layers'), list)
            or config.get('config', {}).get('Labels', {}).get('org.opencontainers.image.revision')
                != record['recipe_revision']):
        raise ValueError('Exact OCI identity and retained recipe label required')
    return manifest


def remote_absent(returncode, stderr):
    return returncode != 0 and b'manifest unknown' in stderr.lower() and not any(
        word in stderr.lower() for word in (b'unauthorized', b'authentication', b'denied'))


def inspect(reference, *, config=False):
    command = ['skopeo', 'inspect', '--raw']
    if config:
        command.append('--config')
    return subprocess.run(command + [reference], stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def publish_one(record, output):
    validate_record(record)
    directory = output / record['name']
    directory.mkdir(parents=True, exist_ok=True)
    source = 'containers-storage:' + record['config_digest'][7:]
    local_manifest, local_config = inspect(source), inspect(source, config=True)
    if local_manifest.returncode or local_config.returncode:
        raise ValueError('Immutable local artifact is missing')
    verify_bytes(record, local_manifest.stdout, local_config.stdout)
    (directory / 'local-manifest.json').write_bytes(local_manifest.stdout)
    (directory / 'local-config.json').write_bytes(local_config.stdout)
    destination = 'docker://' + record['destination']
    previous = inspect(destination)
    already_present = previous.returncode == 0
    if already_present:
        if previous.stdout != local_manifest.stdout:
            raise ValueError('Existing qualification tag differs; overwrite forbidden')
    elif not remote_absent(previous.returncode, previous.stderr):
        raise ValueError('Registry preimage is not an authenticated missing tag')
    started = time.monotonic()
    if not already_present:
        with (directory / 'copy.log').open('wb') as log:
            subprocess.run(['skopeo', 'copy', '--all', '--preserve-digests', '--retry-times', '3',
                            source, destination], stdout=log, stderr=log, check=True)
    remote_manifest, remote_config = inspect(destination), inspect(destination, config=True)
    if remote_manifest.returncode or remote_config.returncode:
        raise ValueError('Published artifact cannot be read back')
    verify_bytes(record, remote_manifest.stdout, remote_config.stdout)
    if remote_manifest.stdout != local_manifest.stdout or remote_config.stdout != local_config.stdout:
        raise ValueError('Remote manifest or config bytes changed')
    (directory / 'remote-manifest.json').write_bytes(remote_manifest.stdout)
    (directory / 'remote-config.json').write_bytes(remote_config.stdout)
    result = dict(record, immutable_reference=record['destination'].partition(':')[0]
        + '@' + record['manifest_digest'], already_present=already_present,
        remote_manifest_bytes_equal=True, remote_config_bytes_equal=True,
        layers_equal=True, elapsed_seconds=round(time.monotonic() - started, 3),
        qualified_scope='publication of existing CPU-tested OCI overlay; no live qualification')
    (directory / 'receipt.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    records = json.loads(args.plan.read_text())['records']
    for record in records:
        validate_record(record)
    if len({record['name'] for record in records}) != len(records) or len(
            {record['destination'] for record in records}) != len(records):
        raise ValueError('Duplicate qualification artifact or destination')
    args.output.mkdir(parents=True, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = {pool.submit(publish_one, record, args.output): record['name'] for record in records}
        results, failures = [], []
        for future in concurrent.futures.as_completed(futures):
            name = futures[future]
            try:
                results.append(future.result())
                print(name + ': published and immutable bytes verified', flush=True)
            except Exception as error:
                failures.append(dict(name=name, error_type=type(error).__name__, error=str(error)))
                print(name + ': publication failed (' + type(error).__name__ + ')', flush=True)
        (args.output / 'results.json').write_text(json.dumps(
            {'results': sorted(results, key=lambda record: record['name']), 'failures': failures},
            indent=2, sort_keys=True) + '\n')
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
