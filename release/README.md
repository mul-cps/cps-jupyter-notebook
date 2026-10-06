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

Existing runtime Dockerfiles are legacy images. The compute overlay is the
released runtime route; target metadata is outside automatic publishing.
RTC presence and addon packaging are checked during build; collaboration,
visitor identity, fresh kernels, storage and GPU isolation require staging.
