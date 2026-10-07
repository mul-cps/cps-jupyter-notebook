# Notebook runtime pilot release

Target 0.1.0 is **not released or qualified**. Populate a reviewed copy of
`targets.json` with every existing variant's immutable base image digest, the
central policy hash, and all released wheel files/SHA256 values. The wheelhouse
must contain cps-compute 0.1.0 with its prebuilt addon, a pinned RTC
`jupyter-collaboration` wheel, and the complete compatible dependency closure.
No package download occurs inside the overlay build. The same wheelhouse and
source tag are applied to all variants, including the narrow MuJoCo image.

On a clean tagged checkout run `python3 release/build.py --lock LOCK
--wheelhouse WHEELS --output OUTPUT` to validate. Add `--build` only on an
operator-approved builder. The script creates local OCI archives, embedded SBOM
and provenance attestations, immutable image digests and SHA256SUMS. It does not
publish images, create releases or execute GPUs. Tags are created only after the
platform acceptance gates, source review and release qualification succeed.

For a private BuildKit daemon, add `--buildctl-address ADDRESS` to the same
command, for example `podman-container://cps-notebook-buildkit`. This uses
`buildctl` directly rather than Docker Buildx, while retaining offline RUN
execution, OCI output, SBOM/provenance attestations and metadata files. All
source-tag, clean-checkout, digest and wheelhouse gates still apply. Use only
reviewed inputs with the private operator builder; public PRs remain on hosted
validation runners.

For large images whose SPDX document exceeds BuildKit's 80 MiB embedded
attestation limit, add `--standalone-sbom --syft /path/to/syft
--syft-sha256 REVIEWED_EXECUTABLE_SHA256`. Verify the scanner's official release
archive checksum before extracting it and reviewing the executable checksum.
Provenance remains embedded; full package/file cataloging produces separate
SPDX and native Syft JSON documents beside each OCI archive. The scanner's
configuration is isolated from ambient Syft settings, and its archive-entry
limit is bounded at 16 GiB for the large reviewed CUDA layers.

The build fails if scanning fails, the SBOM source differs from the OCI image,
or the SPDX package inventory omits native scan results. `release.json` records
the scanner checksum, image binding, package count and both SBOM checksums.
`SHA256SUMS` includes the standalone files; publish them together with the image
and provenance. This option does not waive runtime or release qualification.

Publish each standalone pair as an OCI referrer to the exact image index digest
after image publication. Use a checksum-verified ORAS release and the existing
registry credential file; never put credentials in command arguments. From the
artifact directory, for example:

```bash
oras attach --registry-config "$REGISTRY_AUTH_FILE" \
  --artifact-type application/spdx+json --format json \
  --export-manifest VARIANT.sbom-referrer.json \
  REGISTRY/IMAGE@sha256:VERIFIED_INDEX_DIGEST \
  VARIANT.sbom.spdx.json:application/spdx+json \
  VARIANT.sbom.syft.json:application/vnd.syft+json
```

Retain the returned referrer digest and verify its manifest `subject.digest`
matches the image index. Pull that referrer by digest into a separate directory
with `oras pull --output DIRECTORY REGISTRY/IMAGE@sha256:REFERRER_DIGEST` and
compare both downloaded file hashes against `release.json` and `SHA256SUMS`.
An image push alone does not publish these documents. Archive the attachments
and checksums with the release assets as well. See the canonical
[ORAS attach documentation](https://oras.land/docs/commands/oras_attach/).

Existing runtime Dockerfiles are legacy images. The compute overlay is the
released runtime route; target metadata is outside automatic publishing.
RTC presence and addon packaging are checked during build; collaboration,
visitor identity, fresh kernels, storage and GPU isolation require staging.

A single reviewed wheelhouse may include multiple ABI wheels for the same
canonical package name and version, such as CPython 3.12 and 3.13 binaries.
The validator emits one pinned requirement with every reviewed wheel checksum;
offline pip selects its compatible wheel under `--require-hashes`. Conflicting
package versions still fail validation. Every wheel is checked, including ABI
wheels not selected by the current interpreter. This preserves a common SDK,
addon, RTC and dependency version set across the variant matrix without forcing
incompatible binary wheels onto a different Python runtime. It does not prove
that every variant has a compatible dependency closure: offline installation,
`pip check`, startup and runtime qualification remain mandatory for each image.

Wheel identity comes from exactly one top-level `.dist-info/METADATA` record.
Nested metadata for vendored libraries (for example in Bleach or Setuptools)
does not identify the outer wheel or introduce a separately pinned package.
Missing or multiple top-level records remain invalid. This is required for the
complete offline Jupyter/RTC dependency closure, not just the SDK wheel.
