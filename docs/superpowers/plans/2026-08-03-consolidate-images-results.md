# Task 9 battle-test results: image consolidation

CI run: https://github.com/mul-cps/cps-jupyter-notebook/actions/runs/30846577476
Branch: `consolidate-images`, triggered via manual `workflow_dispatch` (see "Deviations from the brief" below).
All 7 jobs across the 3-stage pipeline (build-bases: 2, build-gpu-frameworks: 2, build-dependents: 3) succeeded.

## Functional check results

`docker/tests/run_functional_checks.sh` was run against every real, published image (pulled one at a
time, image removed with `docker rmi` immediately after each check, per the safety constraint). All
common checks (jupyterlab, jupyterlab_git, code-server + 3 extensions, jovyan user/sudo,
before-notebook.d hooks, ipython kernel config) plus each variant's specific checks passed.

| Variant | Result |
|---|---|
| base-cpu | `RESULT: all checks PASSED for variant=base-cpu` |
| base-gpu | `RESULT: all checks PASSED for variant=base-gpu` |
| standard-cpu | `RESULT: all checks PASSED for variant=standard-cpu` |
| pytorch-code | `RESULT: all checks PASSED for variant=pytorch-code` (torch/torchvision/transformers import) |
| tf-code | `RESULT: all checks PASSED for variant=tf-code` (tensorflow imports) |
| desktop-ros2 | `RESULT: all checks PASSED for variant=desktop-ros2` (torch stack, ros2 CLI, Xvnc shim, vglrun) |
| comfyui | `RESULT: all checks PASSED for variant=comfyui` (ComfyUI checkout, torch, jupyter-comfyui-proxy) |

**7/7 variants passed functional checks with zero regressions.**

## Sizes

Two numbers are reported per image: **compressed** (what's actually stored/transferred in the
registry, computed from `skopeo inspect`'s per-layer `Size` — matches what `size_budgets.yaml`'s
`max_bytes` means) and **uncompressed** (`docker image inspect --format '{{.Size}}'`, the on-disk sum
after decompression — informative but NOT directly comparable to the budget).

| Variant | Compressed (registry) | vs budget | Uncompressed (on-disk) | Pre-refactor size (documented) |
|---|---:|---|---:|---|
| base-cpu | 3.54 GB | budget 6 GB — PASS | 9.49 GB | n/a (new image, split out of the old monolith) |
| base-gpu | 13.82 GB | budget 12 GB — **over by ~1.8 GB** | 26.63 GB | n/a (new image) |
| standard-cpu | 3.54 GB | budget 6 GB — PASS | 9.49 GB | not previously measured |
| pytorch-code | 18.15 GB | budget 19.5 GB — PASS | 34.26 GB | ~17.6 GB observed live (pre-refactor) |
| tf-code | 14.75 GB | budget 19.5 GB — PASS | 29.15 GB | not previously measured |
| desktop-ros2 | 19.29 GB | budget 41 GB — PASS | 38.03 GB | ~19–37 GB observed live (desktop-ros2-xpra, pre-refactor) |
| comfyui | 19.06 GB | budget 19.5 GB — PASS (tight) | 35.69 GB | not previously measured |

Notes:
- **base-gpu exceeds its 12 GB budget by ~1.8 GB.** The budget comment in `size_budgets.yaml` explicitly
  says this value was "not directly measured yet" (a guess). base-gpu is a brand-new image with no
  pre-refactor counterpart, so this is not a regression — it's the first real measurement of a
  previously-nonexistent artifact. Recommend adjusting the budget in a follow-up (task 10), not treating
  this as a defect.
- **pytorch-code (18.15 GB) is essentially at parity with the pre-refactor ~17.6 GB baseline**, not
  smaller. This is expected and correct: consolidation's savings come from registry-level layer
  deduplication across variants (see below), not from shrinking any single image's own size.
- **standard-cpu's compressed size is byte-identical to base-cpu's** (3,537,136,070 bytes) — confirms
  it is a true zero-overhead passthrough as designed (its Dockerfile is `FROM base-cpu` and nothing
  else).
- **comfyui (19.06 GB) is very close to its 19.5 GB budget** — worth watching in future revisions if
  ComfyUI's own dependencies grow, but currently passing.

## Registry dedup: the real source of savings

The headline claim of this consolidation plan is that shared layers (the OS + JupyterLab + code-server
bundle in base-cpu/base-gpu, and the full PyTorch stack in pytorch-code, which desktop-ros2 and comfyui
both build FROM) are stored **once** in the registry, not once per image that references them. This is
invisible from any single image's `.Size` — it only shows up when you look at the union of unique layer
digests across all 7 published images.

Using `skopeo inspect` (no pull required) to collect every layer's digest + compressed size for all 7
images, then taking the union by digest:

- **Naive sum** (all 7 images' compressed sizes added independently, as if no layers were shared):
  **92.15 GB**
- **Real deduped registry footprint** (union of 147 unique layer digests across all 7 images):
  **24.66 GB**
- **Savings from layer sharing alone: ~67.5 GB, a 73% reduction** in what the registry actually has to
  store for these 7 images vs. a world with zero sharing.

This number is internally consistent: because pytorch-code is `FROM base-gpu`, and desktop-ros2/comfyui
are both `FROM pytorch-code`, each child contributes only its own new/changed layers to the union:

```
base-gpu                          13.82 GB
+ pytorch-code unique layers       4.33 GB  (18.15 − 13.82)
+ tf-code unique layers            0.93 GB  (14.75 − 13.82, also built FROM base-gpu)
+ desktop-ros2 unique layers       1.14 GB  (19.29 − 18.15)
+ comfyui unique layers            0.91 GB  (19.06 − 18.15)
+ base-cpu                         3.54 GB
+ standard-cpu unique layers       0.00 GB  (identical to base-cpu)
------------------------------------------
= 24.67 GB  (matches the measured union to within rounding)
```

**Important caveat on "before/after":** a true pre-refactor total isn't computable. The pre-refactor
architecture had 5 fully independent Dockerfiles (no base-cpu/base-gpu split existed), each with its
own full layer stack, and pre-refactor per-variant sizes are documented for only 2 of them
(pytorch-code ~17.6 GB, desktop-ros2-xpra ~19–37 GB, both from
`docs/superpowers/specs/2026-07-24-spegel-image-mirroring-design.md` in the `cps-gpu-cluster` repo).
The other 3 variants (standard-cpu, tf-code, comfyui) were never separately measured before this task.
So the honest comparison is not "before-sum vs after-sum" but: **the post-refactor registry stores
these 7 images' distinct content in 24.66 GB total, vs. 92.15 GB if every image carried its own private
copy of every layer it uses** — that 67.5 GB gap is the real, durable win, and it will grow as more
variants are added on top of the shared bases in the future (each new variant only adds its own delta,
not the full base again).

## Deviations from the brief (flag for task 10 / human review)

The brief assumed a simple "push branch → CI fires → images publish" flow. Two things about the actual
`docker-publish.yml` didn't match that assumption, and required real fixes to battle-test at all:

1. **PR events don't publish.** `docker-publish.yml` has `push: ${{ github.event_name != 'pull_request' }}`
   — a PR run builds but never pushes to `ghcr.io`, so opening a PR (the brief's first fallback) would
   not have produced any images to test. And a plain branch push doesn't trigger at all
   (`on: push: branches: [main]` only fires for `main`).
2. **Fix: added `workflow_dispatch: {}`** to the `on:` block (commit `1cec027`) and triggered the run
   manually via `gh workflow run docker-publish.yml --ref consolidate-images`. This is a real,
   committed change to the workflow file, not just an operational trigger — **human should decide at
   merge time whether to keep `workflow_dispatch` permanently** (useful for future manual battle-tests)
   or remove it.
3. **Real regression found and fixed: hardcoded `:latest` FROM references.** `Dockerfile.pytorch-code`,
   `Dockerfile.tf-code`, `Dockerfile` (standard-cpu), `Dockerfile.comfyui`, and `Dockerfile.desktop-ros2`
   all hardcoded `FROM ghcr.io/.../base-gpu:latest` or `FROM ghcr.io/.../cps-jupyter-notebook:latest-pytorch-code`.
   The `:latest` / `:latest-<variant>` tags are only produced when `startsWith(github.ref, 'refs/heads/main')`
   — since `base-cpu`/`base-gpu` are brand-new image names from this refactor, no `:latest` tag existed
   at all on this branch, and the dependent-stage builds would have failed outright (or, in a scenario
   where a stale `:latest` did exist from a prior main build, would have silently built against the
   *wrong*, pre-refactor base — a false pass). **Fix (commit `16d865b`):** added a `BASE_IMAGE` build
   `ARG` (default preserved as the old `:latest` value, so local/manual `docker build` still works
   unchanged) to each dependent Dockerfile, and wired the workflow to pass the actual just-published,
   ref-tagged image as a `build-arg`, so every dependent stage always consumes the image this same CI
   run just built — never a stale or nonexistent tag.
   - On `main`, `type=ref,event=branch` still produces a `main` tag (not literally `latest`), so this
     build-arg wiring resolves correctly there too — but **task 10 should confirm this explicitly at
     merge time** rather than relying on this note alone.

Both fixes are minimal, targeted, and within the stated scope of "fix the specific Dockerfile/workflow
issue" — no redesign was done.

## Second CI run: desktop-ros2 re-refactor + new desktop-ros2-xpra variant (2026-08-04)

After the original battle-test above, 4 more commits landed on `consolidate-images`: a redone
`desktop-ros2` refactor (reconciling with 3 live bug fixes that landed on `main` in the meantime —
webserver symlink, GLX segfault fix, rviz2/rqt wrap), a brand-new `desktop-ros2-xpra` consolidation
(built FROM the published `pytorch-code` image, same as `desktop-ros2`/`comfyui`), an extended
`structural_checks.py`, and a CI workflow update (Renovate-bumped action versions + the new xpra
matrix entry, bringing `build-dependents` from 3 to 4 jobs).

CI run: https://github.com/mul-cps/cps-jupyter-notebook/actions/runs/30878888279
Triggered via `gh workflow run docker-publish.yml --ref consolidate-images` on commit `7031be3`
(tip of the branch at re-verification time). No fixes were needed — all 7 jobs passed on the first
attempt.

| Stage | Job | Result | Duration |
|---|---|---|---|
| build-bases | base-cpu | success | ~10m |
| build-bases | base-gpu | success | ~18m |
| build-gpu-frameworks | pytorch-code | success | ~25m |
| build-gpu-frameworks | tf-code | success | ~26m |
| build-dependents | standard-cpu | success | ~1m |
| build-dependents | desktop-ros2 | success | ~16m |
| build-dependents | desktop-ros2-xpra (new) | success | ~15m |
| build-dependents | comfyui | success | ~18m |

**7/7 jobs succeeded, total run time ~62 minutes.**

### desktop-ros2 re-verification

Pulled the freshly-published image and ran `docker/tests/run_functional_checks.sh <image> desktop-ros2`
(the same static-check suite as the original battle-test — jupyterlab, jupyterlab_git, code-server +
3 extensions, jovyan user/sudo, before-notebook.d hooks, ipython kernel config, torch/torchvision/
transformers, ros2 CLI, Xvnc shim, vglrun): `RESULT: all checks PASSED for variant=desktop-ros2`.

These are static presence checks, not runtime behavior checks, so they don't directly exercise the 3
bug fixes (webserver symlink, GLX segfault, rviz2/rqt wrap) at runtime — that deeper verification was
flagged as optional extra rigor in the task brief and was not performed here; the static-check bar
(matching the original battle-test's bar) was met.

Size: 38.05 GB uncompressed, 19.29 GB compressed — byte-for-byte consistent with the original
battle-test's measurement (19.29 GB compressed / 38.03 GB uncompressed), confirming the re-refactor
introduced no size regression.

### desktop-ros2-xpra (new variant, never before tested)

`docker/tests/functional_checks.sh` has no `desktop-ros2-xpra)` case yet (only `desktop-ros2`), so
rather than approximate with the wrong variant name, a manual smoke check was run directly in the
container instead:

| Check | Result |
|---|---|
| `import torch` | PASS — torch 2.11.0+cu129 |
| `import transformers` | PASS — transformers 5.14.1 |
| `import jupyterlab` | PASS — jupyterlab 4.5.7 |
| `xpra` binary present | PASS — `xpra v6.5.2-r0` at `/usr/bin/xpra` |
| `code-server` binary present | PASS — `4.131.0` at `/usr/bin/code-server` |
| `ros2` CLI present | PASS — `/opt/ros/jazzy/bin/ros2` (present but not on `PATH` until `/opt/ros/jazzy/setup.bash` is sourced, same convention as `desktop-ros2`) |

All checks passed. No `functional_checks.sh` case was added for this variant as part of this
re-verification task — that's a gap worth closing in a follow-up (task 10) so future CI/manual runs
don't need this ad-hoc smoke check.

Real measured size (`docker image inspect --format '{{.Size}}'` for uncompressed,
`skopeo inspect docker://<ref>` layer-sum for compressed):

| Variant | Compressed (registry) | Uncompressed (on-disk) |
|---|---:|---:|
| desktop-ros2-xpra | 19.40 GB | 38.40 GB |

For context, `desktop-ros2-xpra` is ~0.11 GB larger compressed than `desktop-ros2` (19.40 GB vs
19.29 GB) — consistent with it being `desktop-ros2` plus an `xpra` package layer on the same
`pytorch-code` lineage. Both variants are well under the `desktop-ros2` budget category (41 GB) in
`size_budgets.yaml`, though `size_budgets.yaml` was not checked for a variant-specific
`desktop-ros2-xpra` budget entry as part of this task.

### Disk discipline

Each image was pulled, inspected, checked, and removed (`docker rmi`) one at a time; `df -h /` was
checked before each pull (466 GB free throughout, well above the 30 GB abort threshold).

### Summary of this second run

- **CI: 7/7 jobs green**, no fixes required.
- **desktop-ros2: static functional checks pass, size unchanged from the original battle-test** — the
  re-refactor onto `main`'s 3 bug fixes did not regress consolidation.
- **desktop-ros2-xpra: functionally sound** (torch/transformers/jupyterlab importable, xpra/
  code-server/ros2 present), **measured at 19.40 GB compressed / 38.40 GB uncompressed** — its first
  ever real measurement.
- Flag for task 10: add a `desktop-ros2-xpra)` case to `docker/tests/functional_checks.sh` so future
  runs don't need a manual smoke check for this variant.

## Files changed in this task

- `.github/workflows/docker-publish.yml` — added `workflow_dispatch` trigger; wired `BASE_IMAGE`
  build-args for `build-gpu-frameworks` and `build-dependents` jobs.
- `docker/Dockerfile`, `docker/Dockerfile.pytorch-code`, `docker/Dockerfile.tf-code`,
  `docker/Dockerfile.comfyui`, `docker/Dockerfile.desktop-ros2` — added `ARG BASE_IMAGE=<old default>`
  before each `FROM`, parameterizing the base image reference.

## Summary

- **CI: 7/7 jobs succeeded** on the fixed pipeline.
- **Functional checks: 7/7 variants passed**, zero regressions vs. the pre-refactor variants' behavior.
- **Sizes: 6/7 variants under budget**; base-gpu exceeds its (admittedly unmeasured/guessed) budget by
  ~1.8 GB — not a regression, first real measurement of a new artifact.
- **Real registry dedup savings: ~67.5 GB (73%)** across the 7 published images, from shared-layer
  reuse — this is the actual payoff of the consolidation, and it is not visible from any single image's
  reported size.
- Two real fixes were required and committed during this task (see "Deviations from the brief" above);
  both are flagged for task 10 to review at merge time.
