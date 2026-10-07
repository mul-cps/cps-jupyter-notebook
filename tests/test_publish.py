import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PUBLISH = ROOT / 'release/publish.py'
OCI = 'application/vnd.oci.image.manifest.v1+json'
DOCKER = 'application/vnd.docker.distribution.manifest.v2+json'
INDEX = 'application/vnd.oci.image.index.v1+json'
PREDICATE = 'urn:cps:attestation:notebook-manifest-conversion:v1'


def encoded(value):
    return json.dumps(value, separators=(',', ':')).encode()


def sha(data):
    return 'sha256:' + hashlib.sha256(data).hexdigest()


class PublishTests(unittest.TestCase):
    def verifier(self):
        self.assertTrue(PUBLISH.exists(), 'conversion-chain verifier missing')
        spec = importlib.util.spec_from_file_location('notebook_publish', PUBLISH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.verify_conversion_chain

    def fixture(self, root, *, original_subject=None, invalid_layer=False, outer_schema=2, attestation_schema=2):
        blobs = {}
        def blob(value, media):
            data = encoded(value)
            blobs['blobs/sha256/' + sha(data).split(':')[1]] = data
            return {'mediaType': media, 'digest': sha(data), 'size': len(data)}
        config = blob({'architecture': 'amd64', 'os': 'linux', 'config': {'User': '1000', 'Healthcheck': {'Test': ['CMD', 'healthcheck']}}, 'rootfs': {'type': 'layers', 'diff_ids': []}}, 'application/vnd.oci.image.config.v1+json')
        layers = [{'mediaType': 'application/vnd.oci.image.layer.v1.tar+gzip', 'digest': 'sha256:' + c * 64, 'size': n} for c, n in [('a', 1), ('b', 2)]]
        if invalid_layer:
            layers[0]['digest'] = 'invalid'
        original = {'schemaVersion': 2, 'mediaType': OCI, 'config': config, 'layers': layers}
        image = blob(original, OCI)
        provenance = blob({'_type': 'https://in-toto.io/Statement/v1', 'predicateType': 'https://slsa.dev/provenance/v1', 'subject': [{'name': '_', 'digest': {'sha256': (original_subject or image['digest']).split(':')[1]}}], 'predicate': {'buildDefinition': {'externalParameters': {'request': {'args': {'force-network-mode': 'none'}}}}}}, 'application/vnd.in-toto+json')
        empty = blob({}, 'application/vnd.oci.empty.v1+json')
        attestation = blob({'schemaVersion': attestation_schema, 'mediaType': OCI, 'subject': image, 'artifactType': 'application/vnd.docker.attestation.manifest.v1+json', 'config': empty, 'layers': [{**provenance, 'annotations': {'in-toto.io/predicate-type': 'https://slsa.dev/provenance/v1'}}]}, OCI)
        index = blob({'schemaVersion': 2, 'mediaType': INDEX, 'manifests': [{**image, 'platform': {'architecture': 'amd64', 'os': 'linux'}}, {**attestation, 'platform': {'architecture': 'unknown', 'os': 'unknown'}, 'annotations': {'vnd.docker.reference.type': 'attestation-manifest', 'vnd.docker.reference.digest': image['digest']}}]}, INDEX)
        blobs['index.json'] = encoded({'schemaVersion': outer_schema, 'mediaType': INDEX, 'manifests': [index]})
        archive = root / 'original.oci.tar'
        with tarfile.open(archive, 'w') as target:
            for name, data in blobs.items():
                info = tarfile.TarInfo(name); info.size = len(data)
                target.addfile(info, io.BytesIO(data))
        docker = copy.deepcopy(original)
        docker['mediaType'] = DOCKER
        docker['config']['mediaType'] = 'application/vnd.docker.container.image.v1+json'
        for layer in docker['layers']:
            layer['mediaType'] = 'application/vnd.docker.image.rootfs.diff.tar.gzip'
        docker_path = root / 'docker.json'; docker_path.write_bytes(encoded(docker))
        native = root / 'native.json'; native.write_bytes(encoded({'source': {'metadata': {'imageID': config['digest'], 'manifestDigest': image['digest']}}, 'artifacts': [{'name': 'cps-compute', 'version': '0.1.0'}]}))
        spdx = root / 'spdx.json'; spdx.write_bytes(encoded({'spdxVersion': 'SPDX-2.3', 'packages': [{'name': 'cps-compute', 'versionInfo': '0.1.0'}]}))
        statement = {'_type': 'https://in-toto.io/Statement/v1', 'subject': [{'name': '_', 'digest': {'sha256': sha(docker_path.read_bytes()).split(':')[1]}}], 'predicateType': PREDICATE, 'predicate': {'originalIndex': index['digest'], 'originalManifest': image['digest'], 'originalConfig': config['digest'], 'originalProvenance': provenance['digest'], 'nativeSBOM': sha(native.read_bytes()), 'spdxSBOM': sha(spdx.read_bytes()), 'orderedLayers': [{'digest': x['digest'], 'size': x['size']} for x in layers]}}
        statement_path = root / 'conversion.json'; statement_path.write_bytes(encoded(statement))
        return [archive, docker_path, statement_path, native, spdx], image, docker, statement

    def test_metadata_chain_preserves_original_subject_and_reports_trust_unverified(self):
        verify = self.verifier()
        with tempfile.TemporaryDirectory() as directory:
            paths, original, docker, statement = self.fixture(Path(directory))
            report = verify(*paths)
            self.assertTrue(report['metadataVerified'])
            self.assertEqual(report['originalManifest'], original['digest'])
            self.assertEqual(report['dockerManifest'], sha(paths[1].read_bytes()))
            for gate in ('productionQualified', 'signatureVerified', 'layerPayloadsVerified', 'remoteClosureVerified', 'currentInputBindingsVerified'):
                self.assertIs(report[gate], False)

    def test_rejects_stale_conversion_subject(self):
        verify = self.verifier()
        with tempfile.TemporaryDirectory() as directory:
            paths, original, _, statement = self.fixture(Path(directory))
            statement['subject'][0]['digest']['sha256'] = original['digest'].split(':')[1]
            paths[2].write_bytes(encoded(statement))
            with self.assertRaisesRegex(ValueError, 'subject'): verify(*paths)

    def test_rejects_changed_config_even_with_rebound_conversion_subject(self):
        self.reject_changed_runtime(lambda d: d['config'].update(digest='sha256:' + 'f' * 64), 'config')

    def test_rejects_reordered_layers_even_with_rebound_conversion_subject(self):
        self.reject_changed_runtime(lambda d: d['layers'].reverse(), 'layers')

    def test_rejects_unsupported_layer_conversion(self):
        self.reject_changed_runtime(lambda d: d['layers'][0].update(mediaType='application/vnd.oci.image.layer.v1.tar+zstd'), 'media type')

    def test_rejects_invalid_layer_descriptor_even_when_every_binding_matches(self):
        verify = self.verifier()
        with tempfile.TemporaryDirectory() as directory:
            paths, _, _, _ = self.fixture(Path(directory), invalid_layer=True)
            with self.assertRaisesRegex(ValueError, 'layer descriptor'): verify(*paths)

    def test_rejects_tampered_original_attestation_config(self):
        verify = self.verifier()
        with tempfile.TemporaryDirectory() as directory:
            paths, _, _, _ = self.fixture(Path(directory))
            with tarfile.open(paths[0]) as source:
                members = {m.name: source.extractfile(m).read() for m in source.getmembers()}
            members['blobs/sha256/' + sha(b'{}').split(':')[1]] = b'{"tampered":true}'
            with tarfile.open(paths[0], 'w') as target:
                for name, data in members.items():
                    info = tarfile.TarInfo(name); info.size = len(data)
                    target.addfile(info, io.BytesIO(data))
            with self.assertRaisesRegex(ValueError, 'digest or size'): verify(*paths)

    def test_rejects_invalid_original_index_and_attestation_schema(self):
        verify = self.verifier()
        with tempfile.TemporaryDirectory() as directory:
            for arguments in ({'outer_schema': 1}, {'attestation_schema': 1}):
                with self.subTest(arguments=arguments):
                    paths, _, _, _ = self.fixture(Path(directory), **arguments)
                    with self.assertRaisesRegex(ValueError, 'index|attestation'): verify(*paths)

    def reject_changed_runtime(self, change, error):
        verify = self.verifier()
        with tempfile.TemporaryDirectory() as directory:
            paths, _, docker, statement = self.fixture(Path(directory))
            change(docker); paths[1].write_bytes(encoded(docker))
            statement['subject'][0]['digest']['sha256'] = sha(paths[1].read_bytes()).split(':')[1]
            paths[2].write_bytes(encoded(statement))
            with self.assertRaisesRegex(ValueError, error): verify(*paths)

    def test_rejects_stale_material_and_original_provenance_subject(self):
        verify = self.verifier()
        with tempfile.TemporaryDirectory() as directory:
            paths, _, _, statement = self.fixture(Path(directory))
            statement['predicate']['originalProvenance'] = 'sha256:' + 'f' * 64
            paths[2].write_bytes(encoded(statement))
            with self.assertRaisesRegex(ValueError, 'materials'): verify(*paths)
            paths, _, _, _ = self.fixture(Path(directory), original_subject='sha256:' + 'f' * 64)
            with self.assertRaisesRegex(ValueError, 'provenance subject'): verify(*paths)

    def test_rejects_relabelled_sbom_and_build_provenance_as_conversion(self):
        verify = self.verifier()
        with tempfile.TemporaryDirectory() as directory:
            paths, _, _, statement = self.fixture(Path(directory))
            native = json.loads(paths[3].read_bytes()); native['source']['metadata']['manifestDigest'] = sha(paths[1].read_bytes())
            paths[3].write_bytes(encoded(native))
            statement['predicate']['nativeSBOM'] = sha(paths[3].read_bytes()); paths[2].write_bytes(encoded(statement))
            with self.assertRaisesRegex(ValueError, 'SBOM'): verify(*paths)
            paths, _, _, statement = self.fixture(Path(directory))
            statement['predicateType'] = 'https://slsa.dev/provenance/v1'; paths[2].write_bytes(encoded(statement))
            with self.assertRaisesRegex(ValueError, 'conversion predicate'): verify(*paths)


if __name__ == '__main__':
    unittest.main()
