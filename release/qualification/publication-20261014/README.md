# Immutable qualification publication

These 14 previously tested OCI overlays were published to the existing `mul-cps` repositories. Each remote OCI manifest and image configuration matches its tested local image byte-for-byte; manifest layer descriptors are identical. No images were rebuilt or relabelled. Recipe revision labels remain unchanged.

The receipt records exact source/recipe revisions, config IDs, qualification tags and immutable remote references. Notebook source `3a05d7dfd14ac3f8b6c673cc4ad0818a601b43dd` carries the retained 12-variant CPU qualification and base provenance in `../notebook-oci-20261014`. Its recipe revision remains `4f4ce4c5d48055e9eb62a980fa3cc4741d16d755`. Hub and Source source revisions are recorded separately.

Publication used `skopeo copy --preserve-digests` from each immutable local config ID, with at most two uploads. A mismatched existing qualification tag is rejected. No stable, production or version tag, Hub/Fleet configuration, cluster image or release manifest was changed. Publication adds no connected CPU/GPU/OAuth or production qualification claim.

Validation: 4 publication contract unit tests passed; actual authenticated remote readback passed for all 14 artifacts. Raw manifests/configs and upload logs remain in the private operator evidence directory, with no credentials exported to Git.
