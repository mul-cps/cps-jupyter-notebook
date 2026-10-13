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
  for required in ('force-network-mode=none','attest:sbom=','attest:provenance=mode=max','build-arg:BASE_IMAGE='+lock['baseDigests']['cpu'],'type=oci,name=ghcr.io/mul-cps/cps-jupyter-notebook:cpu-0.1.0,dest=/output/cpu.oci.tar'):
   self.assertIn(required,command)

 def test_buildx_export_has_named_attestation_subject(self):
  lock={'release':'1.0.0-rc.1','policyHash':'sha256:'+'a'*64,'baseDigests':{'base-cpu':'registry/base@sha256:'+'b'*64}}
  command=release.build_command(lock,'base-cpu','reviewed',Path('/context'),Path('/output'))
  self.assertIn('type=oci,name=ghcr.io/mul-cps/cps-jupyter-notebook:base-cpu-1.0.0-rc.1,dest=/output/base-cpu.oci.tar',command)

 def test_unqualified_defaults_cannot_build(self):
  import json
  with self.assertRaisesRegex(ValueError,'policy hash'): release.validate(json.loads((ROOT/'release/targets.json').read_text()),ROOT)
 def test_overlay_is_offline_and_requires_hashed_wheels(self):
  text=(ROOT/'docker/Dockerfile.compute-runtime').read_text()
  self.assertIn('--no-index',text); self.assertIn('--require-hashes',text)
  self.assertIn('--force-reinstall',text)
  uninstall='python -m pip uninstall -y cps-compute cps-compute-jupyterlab'
  self.assertIn(uninstall,text)
  self.assertLess(text.index(uninstall),text.index('pip install'))
  self.assertIn('python /tmp/verify_compute_runtime.py',text)
  verification=(ROOT/'docker/verify_compute_runtime.py').read_text()
  self.assertIn('jupyter_collaboration',verification);self.assertIn('@cps/compute-jupyterlab',verification)
  self.assertIn('papermill',verification);self.assertIn('cps-compute-hub',verification)
 def test_wheels_are_hash_verified_and_include_rtc_addon(self):
  import tempfile, zipfile, hashlib
  import json
  variants=json.loads((ROOT/'release/variants.json').read_text())
  lock={'release':'0.1.0','sourceTag':'v0.1.0','computeVersion':'0.1.0','policyHash':'sha256:'+'a'*64,'variants':variants,'baseDigests':{v:'registry/base@sha256:'+'b'*64 for v in variants},'wheelFiles':{}}
  with tempfile.TemporaryDirectory() as directory:
   wheels=Path(directory)
   lock,wheels=ModularWheelClosureTests().fixture(directory)
   self.assertEqual(len(release.validate(lock,wheels)),5)
   filename=next(iter(lock['wheelFiles']))
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
    digest=hashlib.sha256((wheels/filename).read_bytes()).hexdigest()
    lock['wheelFiles'][filename]=digest
    return digest
   lock,wheels=ModularWheelClosureTests().fixture(directory)
   first=wheel('PyYAML','6.0.3','cp312-cp312-manylinux2014_x86_64')
   second=wheel('pyyaml','6.0.3','cp313-cp313-manylinux2014_x86_64')
   requirements=release.validate(lock,wheels)
   line=next(r for r in requirements if r.startswith('pyyaml=='))
   self.assertEqual(len(requirements),6)
   self.assertIn('--hash=sha256:'+first,line)
   self.assertIn('--hash=sha256:'+second,line)
   wheel('pyyaml','6.0.4','cp313-cp313-manylinux2014_x86_64')
   with self.assertRaisesRegex(ValueError,'version'):
    release.validate(lock,wheels)


class VendoredWheelMetadataTests(unittest.TestCase):
 def test_only_top_level_metadata_identifies_the_wheel(self):
  import tempfile,zipfile,hashlib,json
  variants=json.loads((ROOT/'release/variants.json').read_text())
  lock={'release':'0.1.0','sourceTag':'v0.1.0','computeVersion':'0.1.0','policyHash':'sha256:'+'a'*64,'variants':variants,'baseDigests':{v:'registry/base@sha256:'+'b'*64 for v in variants},'wheelFiles':{}}
  with tempfile.TemporaryDirectory() as directory:
   wheels=Path(directory)
   lock,wheels=ModularWheelClosureTests().fixture(directory)
   for name in ['bleach']:
    filename=name+'-0.1.0-py3-none-any.whl'
    with zipfile.ZipFile(wheels/filename,'w') as archive:
     archive.writestr(name+'-0.1.0.dist-info/METADATA',f'Name: {name}\nVersion: 0.1.0\n')
     archive.writestr(name+'/_vendor/other-9.dist-info/METADATA','Name: other\nVersion: 9\n')
    lock['wheelFiles'][filename]=hashlib.sha256((wheels/filename).read_bytes()).hexdigest()
   requirements=release.validate(lock,wheels)
   self.assertEqual(len(requirements),6)
   self.assertFalse(any(r.startswith('other==') for r in requirements))
   path=wheels/'bleach-0.1.0-py3-none-any.whl'
   with zipfile.ZipFile(path,'a') as archive:
    archive.writestr('second-0.1.0.dist-info/METADATA','Name: second\nVersion: 0.1.0\n')
   lock['wheelFiles'][path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
   with self.assertRaisesRegex(ValueError,'metadata'):release.validate(lock,wheels)

class ModularWheelClosureTests(unittest.TestCase):
 def fixture(self, directory, *, core_assets=False, addon_version='0.1.0', owner='cps-compute-jupyterlab', hub=False, hub_dependency=False, bad_record=False, runner_extra=True, missing_static=False, asset_version=None, core_version='0.1.0'):
  import base64,csv,hashlib,io,json,zipfile
  wheels=Path(directory)
  variants=json.loads((ROOT/'release/variants.json').read_text())
  lock={'release':'0.1.0','sourceTag':'v0.1.0','computeVersion':'0.1.0','policyHash':'sha256:'+'a'*64,'variants':variants,'baseDigests':{v:'registry/base@sha256:'+'b'*64 for v in variants},'wheelFiles':{}}
  names=[('cps-compute',core_version),(owner,addon_version),('jupyter-collaboration','4.4.1'),('papermill','2.6.0'),('ipykernel','6.30.1')]
  if hub:names.append(('cps-compute-hub','0.1.0'))
  for name,version in names:
   normalized=name.replace('-','_');stem=normalized+'-'+version
   files={stem+'.dist-info/METADATA':f'Name: {name}\nVersion: {version}\n'.encode()}
   if name=='cps-compute' and runner_extra:
    files[stem+'.dist-info/METADATA']+=b'Provides-Extra: runner\nRequires-Dist: papermill>=2; extra == "runner"\nRequires-Dist: ipykernel>=6; extra == "runner"\n'
   if hub_dependency and name=='jupyter-collaboration':files[stem+'.dist-info/METADATA']+=b'Requires-Dist: cps_compute_hub>=0.1\n'
   if name==owner or (name=='cps-compute' and core_assets):
    prefix=stem+'.data/data/share/jupyter/labextensions/@cps/compute-jupyterlab/'
    files[prefix+'package.json']=json.dumps({'name':'@cps/compute-jupyterlab','version':asset_version or version}).encode()
    if not missing_static:files[prefix+'static/remoteEntry.abc.js']=b'prebuilt addon'
   rows=[]
   for path,data in files.items():
    digest=base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip('=')
    rows.append([path,'sha256='+('bad' if bad_record and path.endswith('.js') else digest),str(len(data))])
   record=stem+'.dist-info/RECORD';rows.append([record,'','']);buffer=io.StringIO();csv.writer(buffer).writerows(rows);files[record]=buffer.getvalue().encode()
   filename=stem+'-py3-none-any.whl'
   with zipfile.ZipFile(wheels/filename,'w') as archive:
    for path,data in files.items():archive.writestr(path,data)
   lock['wheelFiles'][filename]=hashlib.sha256((wheels/filename).read_bytes()).hexdigest()
  return lock,wheels

 def test_separate_lab_wheel_and_runner_extra_are_pinned(self):
  import tempfile
  with tempfile.TemporaryDirectory() as directory:
   lock,wheels=self.fixture(directory)
   requirements=release.validate(lock,wheels)
   self.assertTrue(any(line.startswith('cps-compute[runner]==0.1.0 --hash=sha256:') for line in requirements))
   self.assertTrue(any(line.startswith('cps-compute-jupyterlab==0.1.0 ') for line in requirements))

 def test_rejects_old_or_duplicate_lab_owner(self):
  import tempfile
  for options in ({'core_assets':True},{'owner':'unrelated-addon'}):
   with self.subTest(options=options),tempfile.TemporaryDirectory() as directory:
    lock,wheels=self.fixture(directory,**options)
    with self.assertRaisesRegex(ValueError,'owner|assets|prebuilt'):release.validate(lock,wheels)

 def test_exact_core_addon_corelease_and_record_are_required(self):
  import tempfile
  for options,error in [({'addon_version':'0.1.1'},'version'),({'asset_version':'0.1.1'},'version'),({'bad_record':True},'RECORD'),({'missing_static':True},'prebuilt'),({'runner_extra':False},'runner')]:
   with self.subTest(options=options),tempfile.TemporaryDirectory() as directory:
    lock,wheels=self.fixture(directory,**options)
    with self.assertRaisesRegex(ValueError,error):release.validate(lock,wheels)

 def test_hub_package_and_transitive_requirement_are_forbidden(self):
  import tempfile
  for options in ({'hub':True},{'hub_dependency':True}):
   with self.subTest(options=options),tempfile.TemporaryDirectory() as directory:
    lock,wheels=self.fixture(directory,**options)
    with self.assertRaisesRegex(ValueError,'Hub'):release.validate(lock,wheels)

 def test_batch_runtime_requires_runner_wheels(self):
  import tempfile
  with tempfile.TemporaryDirectory() as directory:
   lock,wheels=self.fixture(directory)
   del lock['wheelFiles']['papermill-2.6.0-py3-none-any.whl']
   with self.assertRaisesRegex(ValueError,'runner'):release.validate(lock,wheels)


class ReleaseCandidateVersionTests(unittest.TestCase):
 def test_semver_release_and_pep440_wheels_are_the_same_corelease(self):
  import tempfile
  with tempfile.TemporaryDirectory() as directory:
   lock,wheels=ModularWheelClosureTests().fixture(directory,core_version='1.0.0rc1',addon_version='1.0.0rc1',asset_version='1.0.0-rc.1')
   lock.update(release='1.0.0-rc.1',sourceTag='v1.0.0-rc.1',computeVersion='1.0.0rc1')
   requirements=release.validate(lock,wheels)
   self.assertTrue(any(line.startswith('cps-compute[runner]==1.0.0rc1 ') for line in requirements))
   self.assertTrue(any(line.startswith('cps-compute-jupyterlab==1.0.0rc1 ') for line in requirements))

 def test_other_release_candidate_wheel_and_target_versions_are_rejected(self):
  import tempfile
  for addon_version,compute_version in [('1.0.0rc2','1.0.0rc1'),('1.0.0rc1','1.0.0rc2')]:
   with self.subTest(addon_version=addon_version,compute_version=compute_version),tempfile.TemporaryDirectory() as directory:
    lock,wheels=ModularWheelClosureTests().fixture(directory,core_version='1.0.0rc1',addon_version=addon_version)
    lock.update(release='1.0.0-rc.1',sourceTag='v1.0.0-rc.1',computeVersion=compute_version)
    with self.assertRaisesRegex(ValueError,'co-release'):release.validate(lock,wheels)
