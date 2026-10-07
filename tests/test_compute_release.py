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

class StandaloneSbomTests(unittest.TestCase):
 def test_large_sbom_mode_keeps_provenance_and_offline_builds(self):
  import inspect
  self.assertIn('standalone_sbom',inspect.signature(release.build_command).parameters)
  lock={'release':'0.1.0','policyHash':'sha256:'+'a'*64,'baseDigests':{'cpu':'registry/base@sha256:'+'b'*64}}
  for address in (None,'podman-container://private-builder'):
   command=release.build_command(lock,'cpu','reviewed',Path('/context'),Path('/output'),address,standalone_sbom=True)
   self.assertNotIn('attest:sbom=',command);self.assertNotIn('--sbom=true',command)
   self.assertIn('attest:provenance=mode=max' if address else '--provenance=mode=max',command)
   self.assertIn('force-network-mode=none' if address else '--network=none',command)

 def fixture(self, directory):
  import hashlib,io,json,tarfile
  root=Path(directory);archive=root/'cpu.oci.tar'
  config=b'{}';config_digest='sha256:'+hashlib.sha256(config).hexdigest()
  manifest=json.dumps({'config':{'digest':config_digest},'layers':[]}).encode();manifest_digest='sha256:'+hashlib.sha256(manifest).hexdigest()
  index=json.dumps({'manifests':[{'digest':manifest_digest,'platform':{'architecture':'amd64','os':'linux'}}]}).encode()
  with tarfile.open(archive,'w') as target:
   for name,data in [('index.json',index),('blobs/sha256/'+config_digest.split(':')[1],config),('blobs/sha256/'+manifest_digest.split(':')[1],manifest)]:
    info=tarfile.TarInfo(name);info.size=len(data);target.addfile(info,io.BytesIO(data))
  native=root/'cpu.sbom.syft.json';spdx=root/'cpu.sbom.spdx.json'
  native.write_text(json.dumps({'source':{'metadata':{'imageID':config_digest,'manifestDigest':manifest_digest}},'artifacts':[{'name':'cps-compute','version':'0.1.0'}]}))
  spdx.write_text(json.dumps({'spdxVersion':'SPDX-2.3','packages':[{'name':'cps-compute','versionInfo':'0.1.0'}]}))
  return archive,native,spdx

 def test_standalone_sbom_rejects_other_image_and_missing_packages(self):
  import tempfile,json
  self.assertTrue(callable(getattr(release,'verify_standalone_sbom',None)),'standalone SBOM binding verifier missing')
  with tempfile.TemporaryDirectory() as directory:
   archive,native,spdx=self.fixture(directory)
   result=release.verify_standalone_sbom(archive,native,spdx)
   self.assertEqual(result['packages'],1);self.assertEqual(len(result['sha256']),64)
   value=json.loads(native.read_text());value['source']['metadata']['imageID']='sha256:'+'f'*64;native.write_text(json.dumps(value))
   with self.assertRaisesRegex(ValueError,'image'):release.verify_standalone_sbom(archive,native,spdx)
   archive,native,spdx=self.fixture(directory);value=json.loads(spdx.read_text());value['packages']=[];spdx.write_text(json.dumps(value))
   with self.assertRaisesRegex(ValueError,'package'):release.verify_standalone_sbom(archive,native,spdx)

 def test_scanner_checksum_is_required_before_execution(self):
  import tempfile
  self.assertTrue(callable(getattr(release,'generate_standalone_sbom',None)),'standalone SBOM generation missing')
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);tool=root/'untrusted-scanner';marker=root/'executed'
   tool.write_text('#!/bin/sh\ntouch '+str(marker)+'\n');tool.chmod(0o700)
   with self.assertRaisesRegex(ValueError,'checksum'):release.generate_standalone_sbom(root/'cpu.oci.tar',tool,'0'*64)
   self.assertFalse(marker.exists())


class MultiAbiWheelhouseTests(unittest.TestCase):
 def test_same_version_abi_wheels_share_requirement_and_conflicting_versions_fail(self):
  import tempfile,zipfile,hashlib,json
  variants=json.loads((ROOT/'release/variants.json').read_text())
  lock={'release':'0.1.0','sourceTag':'v0.1.0','computeVersion':'0.1.0','policyHash':'sha256:'+'a'*64,'variants':variants,'baseDigests':{v:'registry/base@sha256:'+'b'*64 for v in variants},'wheelFiles':{}}
  with tempfile.TemporaryDirectory() as directory:
   wheels=Path(directory)
   def wheel(name,version,tags):
    filename=name+'-'+version+'-'+tags+'.whl'
    with zipfile.ZipFile(wheels/filename,'w') as archive:
     archive.writestr(name+'.dist-info/METADATA',f'Name: {name}\nVersion: {version}\n')
     if name=='cps_compute':archive.writestr('data/share/jupyter/labextensions/@cps/compute-jupyterlab/package.json','{}')
    digest=hashlib.sha256((wheels/filename).read_bytes()).hexdigest()
    lock['wheelFiles'][filename]=digest
    return digest
   wheel('cps_compute','0.1.0','py3-none-any')
   wheel('jupyter_collaboration','4.4.1','py3-none-any')
   first=wheel('PyYAML','6.0.3','cp312-cp312-manylinux2014_x86_64')
   second=wheel('pyyaml','6.0.3','cp313-cp313-manylinux2014_x86_64')
   requirements=release.validate(lock,wheels)
   line=next(r for r in requirements if r.startswith('pyyaml=='))
   self.assertEqual(len(requirements),3)
   self.assertIn('--hash=sha256:'+first,line)
   self.assertIn('--hash=sha256:'+second,line)
   wheel('pyyaml','6.0.4','cp313-cp313-manylinux2014_x86_64')
   with self.assertRaisesRegex(ValueError,'version'):
    release.validate(lock,wheels)
