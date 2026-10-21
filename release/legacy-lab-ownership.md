# Transfer legacy SDK Lab assets to the addon wheel

Some older notebook images bundle the Compute Lab extension in the
`cps-compute` distribution. Installing the separate addon over those files leaves
the SDK's `RECORD` claiming files whose bytes have changed. Use
`release/legacy_lab_ownership.py` immediately **before** the offline addon wheel
install, in one disposable image-build step. Do not use it against a running
notebook environment.

Root must independently capture the original image's exact raw
`cps_compute-<version>.dist-info/METADATA` and `RECORD` SHA256 values. Do not take
those pins from an image where the addon has already overwritten SDK-owned
files. The pinned RECORD supplies the original per-file hashes and sizes.

Without `--execute` the helper reads and changes no files:

```bash
python -I -B release/legacy_lab_ownership.py
```

In the controlled image build, supply the actual prefix, Python version,
distribution directory, and independently captured hexadecimal pins:

```bash
python -I -B /qualification/legacy_lab_ownership.py \
  --execute \
  --prefix /opt/conda \
  --sdk-dist-info /opt/conda/lib/python3.12/site-packages/cps_compute-0.1.0.dist-info \
  --metadata-sha256 "$ORIGINAL_SDK_METADATA_SHA256" \
  --record-sha256 "$ORIGINAL_SDK_RECORD_SHA256" \
  > /qualification-output/legacy-lab-transfer.json

# Continue in the same build step using the already reviewed offline addon
# wheel/requirements and existing package verification. No SDK uninstall.
```

The example's Python directory is illustrative. It must match the original
image. Keep the image's runtime User and configuration unchanged; the build step
needs permission to modify the original SDK metadata and its owned Lab files.
This helper neither runs pip nor chooses an addon version or wheel.

The execute path:

1. Checks the explicit raw pins and exact `Name: cps-compute` metadata. It parses
   canonical prefix-contained RECORD paths and requires one blank hash/size
   self-RECORD row.
2. Selects only SDK rows whose installed paths are under
   `share/jupyter/labextensions/@cps/compute-jupyterlab/`. Legitimate canonical
   `../../../share/...` wheel paths are supported; absolute paths, aliases and
   prefix escapes are rejected.
3. Rejects ownership of that namespace by any other wheel's RECORD. Unsupported
   legacy egg ownership metadata fails closed. Rejects unrecorded files and all
   symlinks/nonregular assets in the namespace.
4. Verifies **every** selected original asset's SHA256 RECORD hash and byte size
   before deleting anything. Every directory component and file is opened with
   no-follow semantics.
5. Deletes only those original owned files, using their verified directory file
   descriptors. It deletes no directories or parents. It atomically replaces
   only the SDK RECORD, preserving the other original raw CSV lines, including
   their quoting/newlines and the blank self-RECORD row. RECORD owner and mode
   are retained. SDK METADATA is rechecked unchanged.

The deterministic JSON audit contains `version`, `distribution`, the unchanged
`sdk_metadata_sha256`, `previous_record_sha256`, `new_record_sha256`, `changed`,
and a sorted `retired` list. Each retired entry includes its original
`record_path`, prefix-relative `prefix_path`, raw hexadecimal `sha256`, and
`bytes`. It contains no credentials. An SDK with no Lab namespace rows returns a
no-op audit; an already separate addon owner is valid in that no-op case.

After retirement, install the pinned addon in that same build step and retain
the existing wheel RECORD and Lab extension checks. The addon must then own its
installed assets. Independently compare the full original/candidate SDK backend
and native-file inventories and dependency versions; this ownership audit does
not replace that image preservation proof. The intentional changes are legacy
UI asset retirement, the SDK RECORD row removal, and the new addon install.
Do not describe all SDK asset bytes as unchanged.

The helper assumes exclusive access to a disposable build filesystem, with no
concurrent installer. Filesystem failures may occur after an unlink; there is no
live-environment rollback protocol. Stop the build and discard the failed layer
rather than rebinding new pins or running a partial migration again. Generic CLI
failures suppress file contents and do not emit a successful audit.

Focused tests use temporary local fixture files only:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover \
  -s tests -p test_legacy_lab_ownership.py -v
```
