#!/usr/bin/env python3
"""Verify conversion metadata only; never sign, convert, publish or qualify images."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import tarfile

_build_spec = importlib.util.spec_from_file_location('notebook_release_build', Path(__file__).with_name('build.py'))
_build = importlib.util.module_from_spec(_build_spec)
_build_spec.loader.exec_module(_build)
file_sha256, verify_standalone_sbom = _build.file_sha256, _build.verify_standalone_sbom

OCI_MANIFEST = 'application/vnd.oci.image.manifest.v1+json'
OCI_INDEX = 'application/vnd.oci.image.index.v1+json'
DOCKER_MANIFEST = 'application/vnd.docker.distribution.manifest.v2+json'
CONVERSION_PREDICATE = 'urn:cps:attestation:notebook-manifest-conversion:v1'
MAX_METADATA = 2 * 1024 * 1024
MEDIA_CONVERSIONS = {
    'application/vnd.oci.image.config.v1+json': 'application/vnd.docker.container.image.v1+json',
    'application/vnd.oci.image.layer.v1.tar+gzip': 'application/vnd.docker.image.rootfs.diff.tar.gzip',
}


def _digest(data):
    return 'sha256:' + hashlib.sha256(data).hexdigest()


def _json(data):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate metadata key')
            result[key] = value
        return result
    return json.loads(data, object_pairs_hook=unique)


def _file(path):
    if path.stat().st_size > MAX_METADATA:
        raise ValueError('oversized publication metadata')
    return path.read_bytes()


def _subject(statement, digest, error):
    subjects = statement.get('subject', [])
    if (statement.get('_type') != 'https://in-toto.io/Statement/v1'
            or len(subjects) != 1
            or subjects[0].get('digest') != {'sha256': digest.split(':')[1]}):
        raise ValueError(error)


def _layers(manifest):
    layers = manifest['layers']
    for layer in layers:
        if (not re.fullmatch(r'sha256:[a-f0-9]{64}', layer.get('digest', ''))
                or type(layer.get('size')) is not int or layer['size'] < 0):
            raise ValueError('invalid layer descriptor')
    return [{'digest': layer['digest'], 'size': layer['size']} for layer in layers]


def verify_conversion_chain(archive_path, docker_manifest_path, statement_path, native_sbom_path, spdx_sbom_path):
    """Check an unsigned metadata chain, preserving the original build/SBOM subjects.

    All arguments are local files. Descriptor equality does not verify layer
    bytes, signatures, a trusted publisher, remote closure or current inputs.
    """
    paths = [Path(p) for p in (archive_path, docker_manifest_path, statement_path, native_sbom_path, spdx_sbom_path)]
    archive_path, docker_manifest_path, statement_path, native_sbom_path, spdx_sbom_path = paths
    with tarfile.open(archive_path) as archive:
        def raw(name):
            matches = [m for m in archive.getmembers() if m.name == name]
            if len(matches) != 1 or not matches[0].isfile() or matches[0].size > MAX_METADATA:
                raise ValueError('invalid or duplicate OCI metadata member')
            return archive.extractfile(matches[0]).read()

        def blob(descriptor):
            digest = descriptor.get('digest', '')
            if not re.fullmatch(r'sha256:[a-f0-9]{64}', digest):
                raise ValueError('invalid OCI digest')
            data = raw('blobs/sha256/' + digest.split(':')[1])
            if _digest(data) != digest or len(data) != descriptor.get('size'):
                raise ValueError('OCI metadata digest or size differs')
            return _json(data)

        outer = _json(raw('index.json'))
        if outer.get('schemaVersion') != 2 or outer.get('mediaType') != OCI_INDEX or len(outer.get('manifests', [])) != 1:
            raise ValueError('canonical OCI archive index required')
        index_descriptor = outer['manifests'][0]
        if index_descriptor.get('mediaType') != OCI_INDEX:
            raise ValueError('canonical OCI archive index required')
        index = blob(index_descriptor)
        if index.get('schemaVersion') != 2 or index.get('mediaType') != OCI_INDEX:
            raise ValueError('invalid OCI index')
        images = [m for m in index['manifests'] if m.get('platform') == {'architecture': 'amd64', 'os': 'linux'}]
        if len(images) != 1 or images[0].get('mediaType') != OCI_MANIFEST:
            raise ValueError('one amd64 OCI runtime manifest required')
        image = images[0]
        original = blob(image)
        if original.get('schemaVersion') != 2 or original.get('mediaType') != OCI_MANIFEST:
            raise ValueError('invalid original OCI manifest')
        blob(original['config'])
        attestations = [m for m in index['manifests'] if m.get('annotations', {}).get('vnd.docker.reference.type') == 'attestation-manifest']
        if len(attestations) != 1:
            raise ValueError('one original attestation manifest required')
        attestation_descriptor = attestations[0]
        attestation = blob(attestation_descriptor)
        if (attestation.get('schemaVersion') != 2 or attestation.get('mediaType') != OCI_MANIFEST
                or attestation_descriptor.get('mediaType') != OCI_MANIFEST
                or attestation_descriptor.get('annotations', {}).get('vnd.docker.reference.digest') != image['digest']
                or attestation.get('subject') != {key: image[key] for key in ('mediaType', 'digest', 'size')}):
            raise ValueError('original attestation subject differs')
        blob(attestation['config'])
        provenance_layers = [l for l in attestation['layers'] if l.get('annotations', {}).get('in-toto.io/predicate-type') == 'https://slsa.dev/provenance/v1']
        if len(provenance_layers) != 1 or provenance_layers[0].get('mediaType') != 'application/vnd.in-toto+json':
            raise ValueError('one original provenance statement required')
        provenance_descriptor = provenance_layers[0]
        provenance = blob(provenance_descriptor)
        if provenance.get('predicateType') != 'https://slsa.dev/provenance/v1':
            raise ValueError('original provenance predicate differs')
        _subject(provenance, image['digest'], 'original provenance subject differs')

    docker_bytes = _file(docker_manifest_path)
    docker = _json(docker_bytes)
    if docker.get('mediaType') != DOCKER_MANIFEST or docker.get('schemaVersion') != 2:
        raise ValueError('Docker schema2 runtime manifest required')
    if docker.get('config', {}).get('digest') != original['config']['digest'] or docker.get('config', {}).get('size') != original['config']['size']:
        raise ValueError('Docker config differs from original')
    layers = _layers(original)
    if _layers(docker) != layers:
        raise ValueError('Docker ordered layers differ from original')
    expected = copy.deepcopy(original)
    expected['mediaType'] = DOCKER_MANIFEST
    for descriptor in [expected['config'], *expected['layers']]:
        if descriptor.get('mediaType') not in MEDIA_CONVERSIONS:
            raise ValueError('unsupported original media type conversion')
        descriptor['mediaType'] = MEDIA_CONVERSIONS[descriptor['mediaType']]
    if docker != expected:
        raise ValueError('Docker media type or other manifest metadata differs')

    # This existing verifier must inspect the ORIGINAL archive, never Docker D.
    verify_standalone_sbom(archive_path, native_sbom_path, spdx_sbom_path)
    materials = {
        'originalIndex': index_descriptor['digest'],
        'originalManifest': image['digest'],
        'originalConfig': original['config']['digest'],
        'originalProvenance': provenance_descriptor['digest'],
        'nativeSBOM': 'sha256:' + file_sha256(native_sbom_path),
        'spdxSBOM': 'sha256:' + file_sha256(spdx_sbom_path),
        'orderedLayers': layers,
    }
    docker_digest = _digest(docker_bytes)
    statement_bytes = _file(statement_path)
    statement = _json(statement_bytes)
    if statement.get('predicateType') != CONVERSION_PREDICATE:
        raise ValueError('versioned conversion predicate required; build provenance cannot be relabelled')
    _subject(statement, docker_digest, 'conversion subject differs from Docker manifest')
    if statement.get('predicate') != materials:
        raise ValueError('conversion materials differ from original metadata/SBOMs')
    return {**materials, 'dockerManifest': docker_digest, 'conversionStatement': _digest(statement_bytes),
            'metadataVerified': True, 'productionQualified': False, 'signatureVerified': False,
            'layerPayloadsVerified': False, 'remoteClosureVerified': False, 'currentInputBindingsVerified': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('original-archive', 'docker-manifest', 'conversion-statement', 'native-sbom', 'spdx-sbom'):
        parser.add_argument('--' + name, required=True, type=Path)
    args = parser.parse_args()
    try:
        report = verify_conversion_chain(args.original_archive, args.docker_manifest, args.conversion_statement, args.native_sbom, args.spdx_sbom)
    except (ValueError, KeyError, TypeError, IndexError, OSError, tarfile.TarError) as error:
        parser.error(str(error))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
