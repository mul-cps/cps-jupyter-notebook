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
