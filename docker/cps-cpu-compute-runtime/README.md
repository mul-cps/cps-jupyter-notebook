# CPS CPU Compute frontend package candidate

Start from exact d75. Replace only `cps-compute-jupyterlab` using the complete
released wheel `1050c39bb9caed73b0350e5e7dc784e83a62d9c618f0e06f282f7ca3c9a5beaa`
from Compute source `ab0202e56aa20d0e2d4671fb661637830b6bcafc`. The wheel owns its
Python server extension, JSON enablement, dist-info and all prebuilt C7 assets.
Ordinary pip uninstall/install removes stale prebuilt assets and generates
proper RECORD metadata; no asset renaming, string replacement or user override
is installed.

The existing d75 SDK is already version0.1.0 with exact released `sdk.py` hash
`ee0a69ffcd54bdb9a69160086e223a63cbdd4f6bf0ecaacb6a9ecd8963f6b6cc`.
Its RECORD is valid and it owns no Lab assets. Preserve all43 existing Core
Python modules and Core metadata exactly, including CA/resource/storage
behavior. No SDK, scientific, JupyterHub, RTC or dependency version changes
are needed. Keep every original compressed layer descriptor and diffID, full
runtime config, user1000/group100, `/home/jovyan/work`, startup scripts and
inherited Jupyter configuration.

Use an isolated overlay store with the existing d75 cache as a read-only
additional image store. Build the supplied Dockerfile with network disabled,
one job and the hash-locked wheel mounted read-only. Only Compute Lab owned
paths and their required baseline directory headers belong in the portable
delta; include whiteouts for pip-removed stale assets. Ancestor directory
UID/GID/modes must match the real baseline, including the root directory.

Run `inventory.py` and `verify_runtime.py --execute --server-probe` against the
installed image as UID1000 with read-only root and private writable test `/tmp`.
The verifier checks SDK trust, all Compute RECORD rows, sole prebuilt owner,
exact served C7 asset, real local Lab HTML with dedicated visitor and legacy
paths, composed server hook, RTC discovery, Hera rendering and typed Papermill
success plus retained failure. No live OAuth, Hub, Gateway or GPU calls occur.
The released frontend maps the legacy admin path to the dedicated visitor
service; routing still depends on trusted Hub configuration.

This is an offline package candidate. It does not publish/deploy an image,
modify a live notebook, restart any server or change mounts, credentials,
permissions, policy or scientific runtimes. Candidate source/provenance is
recorded separately from unchanged inherited image labels.
