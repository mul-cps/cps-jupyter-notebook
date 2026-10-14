import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

PATH = Path(__file__).parents[1] / 'release/qualification_publication.py'


class PublicationContractTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('qualification_publication', PATH)
        self.publisher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.publisher)
        self.config = json.dumps({'config': {'Labels': {'org.opencontainers.image.revision': 'a' * 40}}}).encode()
        self.manifest = json.dumps({'schemaVersion': 2,
            'mediaType': 'application/vnd.oci.image.manifest.v1+json',
            'config': {'digest': self.publisher.digest(self.config)}, 'layers': []}).encode()
        self.record = dict(name='base-cpu', source_revision='b' * 40, recipe_revision='a' * 40,
            local='localhost/cps-notebook:qualified', manifest_digest=self.publisher.digest(self.manifest),
            config_digest=self.publisher.digest(self.config),
            destination='ghcr.io/mul-cps/cps-jupyter-notebook:base-cpu-qualification-bbbbbbbb-20261014')

    def test_exact_remote_bytes_and_recipe_label_are_required(self):
        self.publisher.validate_record(self.record)
        self.publisher.verify_bytes(self.record, self.manifest, self.config)
        for payload, config in [(self.manifest + b' ', self.config),
                                (self.manifest, self.config + b' ')]:
            with self.assertRaises(ValueError):
                self.publisher.verify_bytes(self.record, payload, config)

    def test_personal_namespace_stable_tag_and_wrong_source_tag_are_rejected(self):
        for destination in ['ghcr.io/bjoernellens1/cps-jupyter-notebook:base-cpu-qualification-bbbbbbbb',
                            'ghcr.io/mul-cps/cps-jupyter-notebook:stable',
                            'ghcr.io/mul-cps/cps-jupyter-notebook:base-cpu-qualification-cccccccc']:
            with self.subTest(destination=destination), self.assertRaises(ValueError):
                self.publisher.validate_record(dict(self.record, destination=destination))

    def test_qualification_cannot_relabel_recipe_source(self):
        with self.assertRaises(ValueError):
            self.publisher.verify_bytes(dict(self.record, recipe_revision='b' * 40),
                                        self.manifest, self.config)

    def test_foreign_remote_tag_is_never_overwritten(self):
        self.assertFalse(self.publisher.remote_absent(1, b'authentication required'))
        self.assertTrue(self.publisher.remote_absent(1, b'manifest unknown'))
        self.assertFalse(self.publisher.remote_absent(0, b'manifest unknown'))


if __name__ == '__main__':
    unittest.main()
