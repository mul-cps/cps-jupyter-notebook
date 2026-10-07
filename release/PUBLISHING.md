# OCI to Docker publication gate

`publish.py` verifies local conversion **metadata**. It does not convert, sign,
publish, build, scan or production-qualify images. Exit status zero means only
that the supplied metadata chain passed. Every report explicitly leaves
signature, layer payloads, remote closure, current input bindings and production
qualification false.

Keep the canonical OCI archive, original platform manifest, BuildKit provenance
and standalone SBOM unchanged. Converting manifest/config/layer media types
changes the runtime manifest digest. Never change an old provenance/SBOM subject
to that new digest, or present conversion evidence as notebook build provenance.
The existing SBOM verifier continues to check the original archive's exact
manifest/config binding.

Run the metadata gate with local files:

```sh
python3 release/publish.py \
  --original-archive original.oci.tar \
  --docker-manifest docker-manifest.json \
  --conversion-statement conversion.json \
  --native-sbom original.sbom.syft.json \
  --spdx-sbom original.sbom.spdx.json
```

The new in-toto Statement/v1 has exactly one subject: the SHA256 of the raw
Docker schema2 manifest bytes. Its predicate type is the versioned local contract
`urn:cps:attestation:notebook-manifest-conversion:v1`. Its predicate contains
exactly these materials, computed from the original artifacts:

```json
{
  "originalIndex": "sha256:<canonical inner OCI index>",
  "originalManifest": "sha256:<original amd64 OCI manifest>",
  "originalConfig": "sha256:<unchanged config blob>",
  "originalProvenance": "sha256:<original BuildKit statement blob>",
  "nativeSBOM": "sha256:<unchanged native SBOM file>",
  "spdxSBOM": "sha256:<unchanged SPDX SBOM file>",
  "orderedLayers": [{"digest": "sha256:<layer>", "size": 123}]
}
```

The verifier hashes bounded original metadata blobs, checks original provenance
subjects and exact SBOM source/package binding, then permits only the reviewed
OCI-to-Docker media-type substitutions. Config digest/size, ordered layer
digests/sizes and all other manifest metadata must remain equal. Only ordinary
gzip OCI layers are supported; other compression or foreign layers fail closed.
Statements are parsed as unsigned JSON; this contract is not a signing identity
or a claim that any supplied statement came from a trusted publisher.

Before implementing publication, establish a reviewed publisher identity,
signature verification and policy for this conversion statement. Bind the actual
current source, wheel and input lock to trusted build evidence; merely echoing
those values in conversion JSON is insufficient. Verify layer/config bytes,
publish and verify the complete original OCI attestation/SBOM descriptor closure,
and test remote immutable digest binding and runtime startup fields including
Healthcheck. A mixed OCI index may carry the Docker runtime and new OCI
conversion-attestation sibling plus the unchanged original canonical subtree;
this tool does not yet verify that index or registry behavior. The original
archive and its attestations remain the source of notebook build/SBOM evidence.
