# Notebook Intelligence startup patch

The deployed NBI 4.6.0 eagerly creates a Claude SDK connection during Jupyter
extension initialization. An unavailable agent delays startup by its 15-second
connection timeout even when Claude is unused. The CPS patch removes only that
constructor call. The existing first-query connection, handshake wait, error
reporting and explicit reconnect paths remain intact.

Build the reviewed upstream wheel with Python and `wheel==0.45.1`:

```sh
python release/build_nbi_wheel.py notebook_intelligence-4.6.0-py3-none-any.whl wheelhouse
python release/qualify_nbi_wheel.py notebook_intelligence-4.6.0-py3-none-any.whl
```

The builder requires the exact upstream SHA256, emits version `4.6.0+cps.2`,
recalculates RECORD through the standard wheel tooling and records provenance
inside dist-info. All other upstream Python and frontend payloads are preserved.
MCP is constrained below 2 and FastMCP below 4 because the upstream code imports
their older APIs. A fresh install of unbounded dependencies failed those imports.

Include the emitted wheel and its complete, hash-pinned dependency closure in the
release lock's `wheelFiles`. The existing offline compute-runtime overlay installs
this through its normal `--require-hashes` requirements, with no startup-time pip
install or site-packages mutation. Verify in a disposable environment:

```sh
python -m pip check
python release/qualify_nbi_lazy_client.py
```

The behavior checks use a controlled SDK and never launch an external agent.
They cover no constructor connection, first-query success, first-query failure,
reconnect and disconnect. They do not qualify actual Claude authentication.

Deployment remains subject to the normal image/policy handover. Measure a fresh
real Hub spawn after promotion; a passing local test alone does not prove the
15-second improvement in the deployed notebook.

`release/nbi-startup.Dockerfile` provides a candidate overlay on the currently
approved digest. Its isolated build context contains only the generated wheel
and `release/qualify_nbi_lazy_client.py` (copied to the context root). It installs
offline without changing dependencies, runs `pip check` and the behavior checks,
and therefore rejects a base whose existing dependencies cannot support the patch.
The local package report does not qualify live promotion. The separately
[qualified candidate image](nbi-startup-image-qualification.json) retains the exact
registry digest, build-container checks and preservation receipts. Live Hub timing
and policy promotion remain separate.

The first `cps.1` candidate was rejected by image `pip check`: the approved base
uses FastMCP 3.2.4, which is compatible with the imported APIs. Revision `cps.2`
permits FastMCP 2.x/3.x and excludes 4.x. Controlled behavior checks pass with
both 2.14.7 and 3.2.4; no base dependency downgrade is required.
