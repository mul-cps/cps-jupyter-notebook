# Native shared-GPU experimental image

This image layer adds the separately packaged `cps-compute` runtime and
`cps-compute-jupyterlab` addon to the digest-pinned image used for the GPU2
MPS feasibility test. It does not enable or qualify a GPU profile. The
native Pod compiler must explicitly select the launcher and the node-side cap
controller remains responsible for enforcing memory limits.

Build the two wheels from a reviewed, compatible `cps-compute` source revision.
Put exactly one `cps_compute-*.whl` in `SDK_WHEEL_DIR` and one
`cps_compute_jupyterlab-*.whl` in `LAB_WHEEL_DIR`, then build with BuildKit:

```sh
docker buildx build --load \
  --build-context compute-wheel="$SDK_WHEEL_DIR" \
  --build-context lab-wheel="$LAB_WHEEL_DIR" \
  --build-arg CPS_COMPUTE_WHEEL_SHA256="$SDK_WHEEL_SHA256" \
  --build-arg CPS_LAB_WHEEL_SHA256="$LAB_WHEEL_SHA256" \
  -f docker/native-shared-gpu/Dockerfile \
  -t cps-native-shared-gpu:qualification docker/native-shared-gpu
```

The wheel hashes must be verified from the reviewed build artifacts before
building. Reinstalling the addon after the SDK restores its ownership of
prebuilt Lab files when the old SDK also owned them. The final image digest,
Pod compiler configuration, cgroup caps, GPU driver, MPS client/server and
workspace lifecycle must be qualified together before this image is enabled.
The control binary is provided by the NVIDIA runtime on the GPU node.

The first experimental candidate was built from image-layer commit `6249240`
and modular SDK/addon source commit `620e6488b82fb8ba49c5cc80317f75b67dabf593`.
The SDK wheel SHA-256 was
`3a658695819e4b78478c93b63c7eea95c7710edb00d3ae30085fe7cb2a19e503`;
the addon wheel SHA-256 was
`3a06c37f4232351bc73551d97a02059ddf5a1b9d023697ef5c916483c049b40d`.
The candidate is available as
`ghcr.io/mul-cps/cps-jupyter-notebook@sha256:d71da8e75b9dcc292bd038fc648a70dce1b7e5e5219d6daa074087c4ba12b568`.
The build passed its default-mode launcher and addon-ownership smoke checks;
it has not passed a GPU test or production qualification.
