# NBI image filesystem evidence

`nbi_filesystem_inventory.py` reads a mounted image without executing its Python
or importing its packages. It records every entry's kind, mode, UID/GID, regular
file or symlink hash, device identity, extended attributes and hardlink topology.
Directory symlinks are not followed. Regular-file reads use checked no-follow
file descriptors, and inode metadata is checked before cached hashes are reused.
Storage-only `trusted.overlay.*` xattrs are explicitly excluded.

The CLI requires an exact dedicated read-only overlay mount and rejects nested
mounts. It writes reproducible gzip evidence outside the image. It does not
validate an arbitrary caller's claimed image reference: the controlled operator
procedure must bind that reference to the actual immutable containerd image and
rootfs chain, retain the raw OCI manifest/config pins and ensure immutable backing
storage. Prefer a private mount namespace.

For containerd inspection, use the explicit immutable digest. Its lower-only
view may report `rw` in mount metadata even without an upperdir; explicitly
remount the temporary view read-only before collecting. Always remove the owned
view and lease using `ctr images unmount --rm --snapshotter overlayfs TARGET`,
including failure paths. Do not delete committed image snapshots or unrelated
leases. No GPU allocation, driver operation or production workload change is
needed for this evidence collection.

Example, after the operator has authenticated the mount:

```sh
python3 release/nbi_filesystem_inventory.py \
  --root /private-inspection/image \
  --image REGISTRY/IMAGE@sha256:EXACT_DIGEST \
  --output /private-evidence/image.json.gz
```

The resulting inventory is evidence for a separate preservation verifier. It is
not a preservation verdict, hardware qualification, image approval or permission
to promote the NBI candidate. The verifier must still bind the exact wheels,
constructor-only patch, complete distribution ownership, layer writes/whiteouts,
all unrelated runtime bytes and configuration to its reviewed contract.
