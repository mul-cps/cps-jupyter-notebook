import importlib.util
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('release',ROOT/'release/build.py')
release=importlib.util.module_from_spec(spec); spec.loader.exec_module(release)
class ReleaseTests(unittest.TestCase):
 def test_buildctl_command_preserves_offline_artifact_contract(self):
  self.assertTrue(hasattr(release, 'build_command'), 'direct BuildKit runner missing')
  lock={'release':'0.1.0','policyHash':'sha256:'+'a'*64,'baseDigests':{'cpu':'registry/base@sha256:'+'b'*64}}
  command=release.build_command(lock,'cpu','reviewed',Path('/context'),Path('/output'),'podman-container://private-builder')
  self.assertEqual(command[:3],['buildctl','--addr','podman-container://private-builder'])
  for required in ('force-network-mode=none','attest:sbom=','attest:provenance=mode=max','build-arg:BASE_IMAGE='+lock['baseDigests']['cpu'],'type=oci,dest=/output/cpu.oci.tar'):
   self.assertIn(required,command)

 def test_unqualified_defaults_cannot_build(self):
  import json
  with self.assertRaisesRegex(ValueError,'policy hash'): release.validate(json.loads((ROOT/'release/targets.json').read_text()),ROOT)
 def test_overlay_is_offline_and_requires_hashed_wheels(self):
  text=(ROOT/'docker/Dockerfile.compute-runtime').read_text()
  self.assertIn('--no-index',text); self.assertIn('--require-hashes',text)
  self.assertIn('jupyter_collaboration',text); self.assertIn('@cps/compute-jupyterlab',text)
 def test_wheels_are_hash_verified_and_include_rtc_addon(self):
  import tempfile, zipfile, hashlib
  import json
  variants=json.loads((ROOT/'release/variants.json').read_text())
  lock={'release':'0.1.0','sourceTag':'v0.1.0','computeVersion':'0.1.0','policyHash':'sha256:'+'a'*64,'variants':variants,'baseDigests':{v:'registry/base@sha256:'+'b'*64 for v in variants},'wheelFiles':{}}
  with tempfile.TemporaryDirectory() as directory:
   wheels=Path(directory)
   for name in ('cps-compute','jupyter-collaboration'):
    filename=name.replace('-','_')+'-0.1.0-py3-none-any.whl'
    with zipfile.ZipFile(wheels/filename,'w') as archive:
     archive.writestr(name.replace('-','_')+'.dist-info/METADATA',f'Name: {name}\nVersion: 0.1.0\n')
     if name=='cps-compute':archive.writestr('data/share/jupyter/labextensions/@cps/compute-jupyterlab/package.json','{}')
    lock['wheelFiles'][filename]=hashlib.sha256((wheels/filename).read_bytes()).hexdigest()
   self.assertEqual(len(release.validate(lock,wheels)),2)
   (wheels/filename).write_text('changed')
   with self.assertRaisesRegex(ValueError,'checksum'):release.validate(lock,wheels)
 def test_public_pr_never_runs_cluster_build_jobs(self):
  text=(ROOT/'.github/workflows/docker-publish.yml').read_text()
  self.assertIn("if: github.event_name != 'pull_request'",text)
if __name__=='__main__': unittest.main()


class ReleaseInventoryTests(unittest.TestCase):
 def test_lock_cannot_omit_existing_variants_or_escape_paths(self):
  import json
  lock=json.loads((ROOT/'release/targets.json').read_text())
  lock['variants']=['../escape'];lock['baseDigests']={'../escape':'registry/base@sha256:'+'b'*64};lock['policyHash']='sha256:'+'a'*64
  with self.assertRaisesRegex(ValueError,'variant'):release.validate(lock,ROOT)
 def test_docs_public_pr_uses_only_hosted_runners(self):
  self.assertNotIn('self-hosted',(ROOT/'.github/workflows/docs.yml').read_text())
 def test_committed_inventory_matches_all_runtime_dockerfiles(self):
  import json
  actual={'standard-cpu' if p.name=='Dockerfile' else p.name.removeprefix('Dockerfile.') for p in (ROOT/'docker').glob('Dockerfile*') if p.name!='Dockerfile.compute-runtime'}
  self.assertEqual(set(json.loads((ROOT/'release/variants.json').read_text())),actual)
