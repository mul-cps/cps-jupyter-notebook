# Native GPU916 Compute package candidate

This candidate starts from the exact approved native GPU image
`ghcr.io/mul-cps/cps-jupyter-notebook@sha256:9167861058c1364c58d1c2fca0d6f536c3ffb53a33800dcdb9a1560f14ca4dc0`.
It replaces only the Compute-owned distribution/assets using the hash-locked
SDK and prebuilt extension from compute source
`ab0202e56aa20d0e2d4671fb661637830b6bcafc`. Framework, CUDA, scientific and RTC
versions and all inherited configuration/startup files remain unchanged.

Build with `Dockerfile` and a `wheelhouse` containing `install.lock` and its two
exact wheels. Installation uses ordinary pip uninstall/install so the SDK no
longer owns the legacy bundled Lab assets; the separate extension distribution
owns the new Python PageConfig hook and prebuilt C7 frontend. The wheel bind
mount leaves no wheel payload or credential in the image. No user-home or
runtime directory overlay is installed. Entrypoint, command, `/workspace`,
environment, user1000, driver/cap configuration and device-init behavior are
inherited.

The cap gate imports its module from the separate trusted gate image. The
notebook-image device identity check uses `python -I -S` and inline stdlib/
absolute libcuda loading. The SDK wheel retains its native Python modules;
none of these helpers requires a driver or kernel change.

Run `inventory.py` in the exact base and candidate. All existing distribution
versions and non-Compute metadata/startup/config hashes must match; only the
new Compute extension distribution/config is added. Run
`verify_runtime.py --execute --server-probe` in the candidate with networking
disabled and a read-only root plus private writable test `/tmp`. It checks the
installed SDK trust handling, prebuilt ownership, native/scientific imports,
ordinary Hera rendering, typed Papermill success/failure retention, and actual
local Lab HTML/entry/RTC loading for direct visitor and legacy Hub routing.
The frontend maps the reviewed legacy admin prefix to the corresponding
dedicated visitor service; browser API identity remains the actual visitor.
Test credentials and CA construction exist only in the verifier process.

Keep all original base layer descriptors and diffIDs in the candidate OCI.
A bounded isolated store may use the existing base cache as an explicitly
read-only additional image store; do not unpack another full GPU base or
modify/prune the global store. Preserve exact base blobs in the portable OCI.
The qualification record must distinguish shared existing base bytes from new
physical allocations and verify every blob descriptor before freezing.

This is a package candidate, not a new GPU qualification or deployment. It
requires a controlled hardware/workspace/browser test and reviewed policy/
image allowlist update before adoption. This preparation does not publish an
image, access live APIs, change grants/configuration, or restart a server.
