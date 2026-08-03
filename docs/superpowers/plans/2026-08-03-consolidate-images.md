# Consolidate cps-jupyter-notebook Images Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate duplicated layers across the 5 `cps-jupyter-notebook` image variants by introducing two shared base images (`base-cpu`, `base-gpu`) and chaining the GPU variants that need PyTorch (`desktop-ros2`, `comfyui`) off the already-built `pytorch-code` image instead of reinstalling PyTorch from scratch, while preserving 100% functional parity (every package, extension, tool, and behavior currently present must still be present). Verify via a purpose-built test suite run against both the pre-refactor (baseline) and post-refactor (real, CI-built) images.

**Architecture:** Two new base Dockerfiles capture everything currently copy-pasted across all 5 variants (common JupyterLab extensions, code-server + its 7 VS Code extensions, `before-notebook.d` hooks, ipython config, Copilot install, sudo setup). `Dockerfile` (standard-cpu) becomes a thin layer on `base-cpu`. `Dockerfile.pytorch-code` and `Dockerfile.tf-code` become thin layers on `base-gpu`. `Dockerfile.desktop-ros2` and `Dockerfile.comfyui` are rebuilt `FROM` the already-published `pytorch-code` image (reusing its PyTorch install as a real, shared, cached layer) instead of `FROM` the raw upstream `gpu-jupyter` base. CI is restructured so the base images (and `pytorch-code`, since two other variants now depend on it) build and publish *before* the variants that need them.

**Tech Stack:** Docker/BuildKit multi-stage builds, GitHub Actions (`docker/build-push-action@v6`), bash + Python test scripts, `docker/metadata-action`.

**Local environment constraint (binding on every task in this plan):** the development machine has only ~77GB free disk. These images range 10-37GB each. **Never** run a real multi-stage GPU image build to completion locally (`docker build` without `--target` on `base-gpu` or any variant that pulls the CUDA base). Structural/static checks run locally. Real builds and functional verification against real images happen through this repo's own GitHub Actions CI (which already has disk-management steps) — trigger a real workflow run and inspect/pull only what's needed to verify, never build the full matrix locally.

## Global Constraints

- Every package/extension/tool currently installed in each of the 5 variants must still be present and at the same version after refactor — this is a build-layer reorganization, not a feature or dependency change. Do not add, remove, or upgrade any package as part of this plan unless a task explicitly says so.
- `NB_USER` is `jovyan` throughout (set by the upstream base images); do not hardcode `jovyan` where `${NB_USER}` is already used in the current files, and vice versa — match each file's existing convention exactly when moving code.
- New base images are named `ghcr.io/mul-cps/cps-jupyter-notebook-base-cpu` and `ghcr.io/mul-cps/cps-jupyter-notebook-base-gpu` (separate GHCR packages from `cps-jupyter-notebook` itself, since they are internal build artifacts, not user-facing profile images — they must never be referenced anywhere in `cps-gpu-cluster`'s JupyterHub profile list).
- `docker/Dockerfile.desktop-ros2`'s existing `ARG INCLUDE_VSCODE_DESKTOP=0` behavior must be preserved exactly (default off, opt-in via build arg).
- Do not touch `docker/Dockerfile.comfyui`'s ComfyUI-specific logic (git clone, ComfyUI-Manager, `jupyter-comfyui-proxy` install, `start-comfyui.sh`) beyond changing its `FROM` line and removing now-duplicated setup that the new base provides.
- All new/modified Dockerfiles must keep using the existing BuildKit cache-mount pattern (`--mount=type=cache,target=...,sharing=locked` for apt, `--mount=type=cache,target=.../.cache/pip` for pip) exactly as the current files do, since this is what makes the existing CI's `cache-from/cache-to: type=gha` effective.
- No task in this plan may run `docker build` to completion locally against `base-gpu`, `pytorch-code`, `tf-code`, `desktop-ros2`, or `comfyui` Dockerfiles (their base image alone is several GB; a full build is 10-37GB). `base-cpu` and `Dockerfile` (standard-cpu, ~1-2GB base) may be built locally if a task needs to.

---

### Task 1: Write the test suite (structural + functional + size-budget), baseline it against the CURRENT published images

**Files:**
- Create: `docker/tests/structural_checks.py`
- Create: `docker/tests/functional_checks.sh`
- Create: `docker/tests/size_budgets.yaml`
- Create: `docker/tests/run_functional_checks.sh`
- Create: `docker/tests/README.md`

**Interfaces:**
- Produces: `structural_checks.py` — run with `python3 docker/tests/structural_checks.py`, exits non-zero with a clear message listing every violation if any Dockerfile in `docker/` violates a structural rule (see Step 1). No external dependencies beyond Python 3 stdlib.
- Produces: `functional_checks.sh` — a script that is COPIED INTO a running container and executed there (`docker exec <container> /tmp/functional_checks.sh <variant-name>`), printing `PASS: <check>` / `FAIL: <check>: <reason>` lines and exiting non-zero if any check fails.
- Produces: `run_functional_checks.sh <image-ref> <variant-name>` — orchestrates: `docker run -d --name test-<variant> <image-ref> sleep 600`, waits for the container to be running, copies in and runs `functional_checks.sh`, prints the pass/fail summary, then always tears the container down (`docker rm -f`) even on failure.
- Consumes (by a later task): `size_budgets.yaml` — a simple `variant: max_bytes` mapping used to flag size regressions once real images are built.

- [ ] **Step 1: Write `structural_checks.py`**

```python
#!/usr/bin/env python3
"""
Static structural checks for docker/Dockerfile*.

Run: python3 docker/tests/structural_checks.py
Exits 0 if all checks pass, 1 with a listed summary of violations otherwise.

These checks do NOT require Docker or any build -- they parse the
Dockerfile text directly, so they can run in any environment (including
disk-constrained local dev machines) as a fast pre-build gate.
"""
import pathlib
import re
import sys

DOCKER_DIR = pathlib.Path(__file__).resolve().parent.parent

# Variants that, after the consolidation refactor, MUST NOT reinstall
# JupyterLab / the shared extension bundle / code-server from scratch --
# they must inherit it from a base image instead. Populated as each
# variant is refactored in later tasks; until refactored, a variant is
# expected to still show these patterns (see EXPECTED_BASELINE below),
# so this check is parametrized rather than hardcoded to "must never
# appear anywhere".
CONSOLIDATED_VARIANTS = {
    "Dockerfile": "ghcr.io/mul-cps/cps-jupyter-notebook-base-cpu",
    "Dockerfile.pytorch-code": "ghcr.io/mul-cps/cps-jupyter-notebook-base-gpu",
    "Dockerfile.tf-code": "ghcr.io/mul-cps/cps-jupyter-notebook-base-gpu",
    "Dockerfile.desktop-ros2": "ghcr.io/mul-cps/cps-jupyter-notebook:latest-pytorch-code",
    "Dockerfile.comfyui": "ghcr.io/mul-cps/cps-jupyter-notebook:latest-pytorch-code",
}

DUPLICATE_MARKERS = [
    "jupyterlab-git",
    "code-server.dev/install.sh",
    "install-copilot.sh",
]

errors = []


def check_from_lines(path, expected_base):
    """The FIRST FROM line (ignoring multi-stage intermediate FROMs that
    reference an earlier stage by name, e.g. `FROM base AS extensions`)
    must reference the expected consolidated base."""
    text = path.read_text()
    from_lines = re.findall(r"^FROM\s+(\S+)", text, re.MULTILINE)
    if not from_lines:
        errors.append(f"{path.name}: no FROM line found at all")
        return
    first = from_lines[0]
    if first != expected_base:
        errors.append(
            f"{path.name}: first FROM is {first!r}, expected {expected_base!r} "
            f"(consolidation base)"
        )


def check_no_duplicate_install(path):
    """A consolidated variant must not re-run the shared install steps
    (they come from its base image now)."""
    text = path.read_text()
    for marker in DUPLICATE_MARKERS:
        if marker in text:
            errors.append(
                f"{path.name}: still contains {marker!r} -- this should now "
                f"come from the base image, not be reinstalled"
            )


def check_pip_cache_mount_present(path):
    """Any RUN pip install line must use the BuildKit pip cache mount,
    matching this repo's existing convention (needed for CI cache-from/
    cache-to: type=gha to be effective)."""
    text = path.read_text()
    for i, line in enumerate(text.splitlines(), start=1):
        if re.match(r"\s*pip install", line):
            # look backwards up to 5 lines for the cache mount on the
            # same RUN statement
            window = "\n".join(text.splitlines()[max(0, i - 6):i])
            if "--mount=type=cache" not in window:
                errors.append(
                    f"{path.name}:{i}: 'pip install' without a preceding "
                    f"--mount=type=cache on the same RUN statement"
                )


def main():
    all_dockerfiles = sorted(DOCKER_DIR.glob("Dockerfile*"))
    found_names = {p.name for p in all_dockerfiles}

    for name, expected_base in CONSOLIDATED_VARIANTS.items():
        path = DOCKER_DIR / name
        if not path.exists():
            errors.append(f"Expected Dockerfile {name!r} not found in {DOCKER_DIR}")
            continue
        check_from_lines(path, expected_base)
        check_no_duplicate_install(path)
        check_pip_cache_mount_present(path)

    # base images must exist once created
    for base_name in ("Dockerfile.base-cpu", "Dockerfile.base-gpu"):
        if base_name not in found_names:
            errors.append(f"Expected base Dockerfile {base_name!r} not found yet")

    if errors:
        print(f"STRUCTURAL CHECKS FAILED ({len(errors)} violation(s)):", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        sys.exit(1)
    print("All structural checks passed.")
    sys.exit(0)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it now and confirm it correctly reports the CURRENT (pre-refactor) state as failing**

Run: `python3 docker/tests/structural_checks.py`
Expected: exits 1, lists violations for every one of the 5 `CONSOLIDATED_VARIANTS` entries (wrong FROM line, duplicate install markers present) plus both missing base Dockerfiles. This confirms the check script actually detects the current, unconsolidated state correctly (a check that can't fail on real bad input is worthless) — this is the "red" side of red/green before any refactor work happens.

- [ ] **Step 3: Write `functional_checks.sh`**

```bash
#!/bin/sh
# docker/tests/functional_checks.sh
#
# Runs INSIDE a container of the image under test. Takes one argument:
# the variant name (standard-cpu | pytorch-code | tf-code | desktop-ros2 |
# comfyui), which selects which checks apply. Prints PASS/FAIL lines,
# exits non-zero if any check fails.
set -u
VARIANT="${1:?usage: functional_checks.sh <variant-name>}"
FAILURES=0

pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1: $2"; FAILURES=$((FAILURES + 1)); }

check_cmd() {
  # check_cmd <label> <command...>
  label="$1"; shift
  if "$@" >/tmp/check_out.$$ 2>&1; then
    pass "$label"
  else
    fail "$label" "command failed: $* -- output: $(cat /tmp/check_out.$$)"
  fi
  rm -f /tmp/check_out.$$
}

check_contains() {
  # check_contains <label> <command...> -- <substring>
  label="$1"; shift
  cmd=""
  substr=""
  seen_dashdash=0
  for arg in "$@"; do
    if [ "$arg" = "--" ]; then seen_dashdash=1; continue; fi
    if [ "$seen_dashdash" = "0" ]; then cmd="$cmd $arg"; else substr="$arg"; fi
  done
  out=$(eval "$cmd" 2>&1)
  case "$out" in
    *"$substr"*) pass "$label" ;;
    *) fail "$label" "expected output to contain '$substr', got: $out" ;;
  esac
}

# ---- Checks that apply to EVERY variant ----
check_cmd "jupyter-lab is importable" python3 -c "import jupyterlab"
check_cmd "jupyterlab_git installed" python3 -c "import jupyterlab_git" 2>/dev/null || check_cmd "jupyterlab-git pip-listed" sh -c "pip show jupyterlab-git"
check_cmd "code-server binary present" sh -c "command -v code-server"
check_contains "code-server has ms-python.python extension" code-server --list-extensions -- "ms-python.python"
check_contains "code-server has ms-toolsai.jupyter extension" code-server --list-extensions -- "ms-toolsai.jupyter"
check_contains "code-server has mhutchie.git-graph extension" code-server --list-extensions -- "mhutchie.git-graph"
check_cmd "jovyan user exists" id jovyan
check_cmd "jovyan is in sudo group" sh -c "id jovyan | grep -q sudo"
check_cmd "before-notebook.d hooks present" sh -c "[ -x /usr/local/bin/before-notebook.d/00-prepare-readonly-home.sh ] && [ -x /usr/local/bin/before-notebook.d/fix-permissions.sh ]"
check_cmd "ipython_kernel_config.py present" sh -c "[ -f /root/.ipython/profile_default/ipython_kernel_config.py ] || [ -f /home/jovyan/.ipython/profile_default/ipython_kernel_config.py ]"

# ---- Variant-specific checks ----
case "$VARIANT" in
  pytorch-code|desktop-ros2)
    check_cmd "torch is importable" python3 -c "import torch; assert torch.__version__.startswith('2.11'), torch.__version__"
    check_cmd "torchvision is importable" python3 -c "import torchvision"
    check_cmd "transformers is importable" python3 -c "import transformers"
    ;;
esac

case "$VARIANT" in
  tf-code)
    check_cmd "tensorflow is importable" python3 -c "import tensorflow as tf; assert tf.__version__.startswith('2.21'), tf.__version__"
    ;;
esac

case "$VARIANT" in
  desktop-ros2)
    check_cmd "ros2 CLI present" sh -c "command -v ros2 || . /opt/ros/jazzy/setup.sh && command -v ros2"
    check_cmd "Xvnc shim present" sh -c "[ -x /usr/local/bin/Xvnc ]"
    check_cmd "vglrun present" sh -c "command -v vglrun"
    ;;
esac

case "$VARIANT" in
  comfyui)
    check_cmd "ComfyUI checked out" sh -c "[ -f /opt/comfyui/main.py ]"
    check_cmd "torch is importable (comfyui)" python3 -c "import torch"
    check_cmd "jupyter-comfyui-proxy installed" sh -c "pip show jupyter-comfyui-proxy"
    ;;
esac

echo "----"
if [ "$FAILURES" -gt 0 ]; then
  echo "RESULT: $FAILURES check(s) FAILED for variant=$VARIANT"
  exit 1
fi
echo "RESULT: all checks PASSED for variant=$VARIANT"
exit 0
```

- [ ] **Step 4: Write `run_functional_checks.sh`**

```bash
#!/bin/sh
# docker/tests/run_functional_checks.sh <image-ref> <variant-name>
#
# Starts a container from <image-ref>, copies in functional_checks.sh,
# runs it for <variant-name>, always tears the container down.
set -eu
IMAGE_REF="${1:?usage: run_functional_checks.sh <image-ref> <variant-name>}"
VARIANT="${2:?usage: run_functional_checks.sh <image-ref> <variant-name>}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONTAINER_NAME="test-${VARIANT}-$$"

cleanup() {
  docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "Starting container from $IMAGE_REF ..."
docker run -d --name "$CONTAINER_NAME" --entrypoint sh "$IMAGE_REF" -c "sleep 600"

echo "Copying functional_checks.sh in..."
docker cp "$SCRIPT_DIR/functional_checks.sh" "$CONTAINER_NAME:/tmp/functional_checks.sh"
docker exec "$CONTAINER_NAME" chmod +x /tmp/functional_checks.sh

echo "Running checks for variant=$VARIANT ..."
docker exec "$CONTAINER_NAME" /tmp/functional_checks.sh "$VARIANT"
```

- [ ] **Step 5: Write `size_budgets.yaml`**

```yaml
# docker/tests/size_budgets.yaml
#
# Maximum acceptable compressed image size (bytes) per variant, used by
# a later task to flag size regressions once real post-refactor images
# are built via CI. Baseline max_bytes values below are set from the
# CURRENT (pre-refactor) live-observed sizes documented in
# docs/superpowers/specs/2026-07-24-spegel-image-mirroring-design.md
# (pytorch-code ~17.6GB observed live; desktop-ros2-xpra ~19-37GB
# observed live) plus a 10% margin -- NOT aspirational targets. The
# post-refactor verification task should report actual sizes achieved
# and by how much they beat these baselines, not just pass/fail.
standard-cpu:
  max_bytes: 6000000000      # 6 GB margin; not directly measured yet
base-cpu:
  max_bytes: 6000000000
base-gpu:
  max_bytes: 12000000000     # 12 GB margin; not directly measured yet
pytorch-code:
  max_bytes: 19500000000     # ~17.6GB observed + ~10%
tf-code:
  max_bytes: 19500000000     # assumed similar order of magnitude to pytorch-code
desktop-ros2:
  max_bytes: 41000000000     # ~37GB observed (xpra variant) + margin; desktop-ros2 itself not separately measured
comfyui:
  max_bytes: 19500000000     # assumed similar order of magnitude to pytorch-code (adds ComfyUI source + deps on top of torch)
```

- [ ] **Step 6: Write `docker/tests/README.md`**

```markdown
# docker/tests

Test suite for the cps-jupyter-notebook image consolidation
(docs/superpowers/plans/2026-08-03-consolidate-images.md).

- `structural_checks.py` -- static, no Docker required. Run locally any
  time: `python3 docker/tests/structural_checks.py`.
- `functional_checks.sh` -- runs INSIDE a container; invoked by
  `run_functional_checks.sh`, not directly.
- `run_functional_checks.sh <image-ref> <variant-name>` -- pulls/runs a
  real image and checks it actually works. **Do not run this against
  base-gpu, pytorch-code, tf-code, desktop-ros2, or comfyui locally** --
  those images are 10-37GB; run it against images already pulled by CI,
  or against the small `standard-cpu`/`base-cpu` images only, on this
  development machine (see the plan's Global Constraints on local disk).
- `size_budgets.yaml` -- size regression budgets, consumed by the final
  verification task once real post-refactor images exist in the
  registry.
```

- [ ] **Step 7: Commit**

```bash
git add docker/tests/
git commit -m "test: add structural, functional, and size-budget test suite for image consolidation"
```

---

### Task 2: Create the shared base Dockerfiles (`base-cpu`, `base-gpu`)

**Files:**
- Create: `docker/Dockerfile.base-cpu`
- Create: `docker/Dockerfile.base-gpu`

**Interfaces:**
- Produces: two images, `ghcr.io/mul-cps/cps-jupyter-notebook-base-cpu:latest` and `ghcr.io/mul-cps/cps-jupyter-notebook-base-gpu:latest`, each containing the full common layer (JupyterLab + shared extensions, code-server + its 7 VS Code extensions, sudo, `before-notebook.d` hooks, ipython config, Copilot install) ready for a variant Dockerfile to `FROM` and add only its unique heavy layer.
- Consumes: nothing new — content is extracted verbatim from the current `docker/Dockerfile` (for base-cpu) and the common portions of `docker/Dockerfile.pytorch-code` / `docker/Dockerfile.tf-code` (for base-gpu, since those two files are currently near-identical outside their ML-framework-specific RUN blocks).

- [ ] **Step 1: Write `docker/Dockerfile.base-cpu`**

This is the current `docker/Dockerfile` (lines 1-79, up through `RUN chown -R jovyan:users /home/jovyan` and the hooks/copilot/VS-Code-extensions block) with the `AS base` stage name kept, and the trailing `WORKDIR`/`USER root` left in place so it's directly usable standalone AND as a base:

```dockerfile
# docker/Dockerfile.base-cpu
#
# Shared base for the CPU-only standard-cpu variant. Contains: the
# common JupyterLab extension bundle, code-server + its 7 VS Code
# extensions, sudo for jovyan, before-notebook.d hooks, ipython config,
# and the Copilot installer. Extracted verbatim from the pre-consolidation
# docker/Dockerfile (docs/superpowers/plans/2026-08-03-consolidate-images.md).
FROM quay.io/jupyter/datascience-notebook:lab-4.5.7 AS base

ENV PIP_ROOT_USER_ACTION=ignore

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade \
    jupyterlab==4.5.7 \
    jupyterlab-git \
    nbgitpuller \
    jupyter-resource-usage \
    catppuccin-jupyterlab \
    jupyterlab-horizon-theme \
    jupyterlab-topbar-text \
    lckr-jupyterlab-variableinspector \
    jupyterlab-image-editor \
    jupyterlab-link-share \
    jupyterlab-spreadsheet-editor \
    jupyterlab-filesystem-access \
    jupyter-archive \
    jlab-enhanced-cell-toolbar \
    jupyterlab-favorites \
    jlab-enhanced-launcher \
    jupyter-sshd-proxy \
    jupyter-server-proxy \
    git+https://github.com/bjoernellens1/jupyter-code-server \
    jupyter-glances-proxy \
    notebook-intelligence \
    git-credential-helpers && \
    if command -v npm >/dev/null 2>&1; then npm cache clean --force; fi && \
    rm -rf $CONDA_DIR/share/jupyter/lab/staging

USER root
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    rm -f /etc/apt/apt.conf.d/docker-clean && \
    apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y \
    --no-install-recommends \
    gh \
    nodejs \
    npm \
    jq \
    btop \
    openssh-server \
    tmux \
    && curl -fsSL https://code-server.dev/install.sh | sh \
    && rm -rf /var/lib/apt/lists/*

RUN usermod -aG sudo jovyan

ENV username=jovyan

RUN --mount=type=secret,id=root_password \
    if [ -f /run/secrets/root_password ] && [ -s /run/secrets/root_password ]; then \
    echo "${NB_USER}:$(cat /run/secrets/root_password)" | chpasswd ; \
    else \
    echo "INFO: /run/secrets/root_password missing or empty, skipping password change"; \
    fi

RUN chown -R jovyan:users /home/jovyan

# Copy pre-notebook hooks
COPY 00-prepare-readonly-home.sh /usr/local/bin/before-notebook.d/
COPY fix-permissions.sh /usr/local/bin/before-notebook.d/
RUN chmod +x /usr/local/bin/before-notebook.d/*.sh

USER jovyan
WORKDIR /home/jovyan/work
COPY ipython_kernel_config.py /root/.ipython/profile_default/ipython_kernel_config.py

# Install Copilot
COPY --chown=jovyan:users install-copilot.sh /tmp/install-copilot.sh
RUN chmod +x /tmp/install-copilot.sh && /tmp/install-copilot.sh && rm /tmp/install-copilot.sh

# Install VS Code extensions
RUN code-server --install-extension ms-python.python && \
    code-server --install-extension ms-toolsai.jupyter && \
    code-server --install-extension charliermarsh.ruff && \
    code-server --install-extension tamasfe.even-better-toml && \
    code-server --install-extension redhat.vscode-yaml && \
    code-server --install-extension ms-azuretools.vscode-docker && \
    code-server --install-extension mhutchie.git-graph

# Switch to root to allow fixing permissions on startup
USER root
WORKDIR /home/jovyan/work
```

- [ ] **Step 2: Write `docker/Dockerfile.base-gpu`**

Extracted from the common portions of `docker/Dockerfile.pytorch-code` and `docker/Dockerfile.tf-code` (everything through the shared extension pip-install and `nb_conda_kernels` step, i.e. lines 1-79 of `Dockerfile.pytorch-code` up to and including the `nb_conda_kernels` RUN block, using the `pytorch-code` file's exact extension list since it's a superset — `jupyterlab-nvdashboard`, `ipywidgets`, `jupyterlab-lsp`, `python-lsp-server[all]`, `black`, `isort`, `ruff`, `notebook-intelligence` — note `tf-code`'s list differs only by using `jupyterlab-code-formatter` instead of nothing extra; since `base-gpu` must be a strict superset both variants can build on without losing anything, include BOTH `jupyterlab-nvdashboard`/`black`/`isort`/`ruff`/`jupyterlab-lsp`/`python-lsp-server[all]`/`notebook-intelligence` from pytorch-code AND `jupyterlab-code-formatter` from tf-code):

```dockerfile
# docker/Dockerfile.base-gpu
#
# Shared base for all GPU/CUDA variants (pytorch-code, tf-code, and
# transitively desktop-ros2/comfyui which build FROM the pytorch-code
# image). Contains the common JupyterLab extension bundle, code-server
# + its 7 VS Code extensions, sudo for jovyan, before-notebook.d hooks,
# ipython config, Copilot installer, and nb_conda_kernels -- everything
# that was previously copy-pasted identically across pytorch-code.
# tf-code, desktop-ros2, and comfyui.
# Union of docker/Dockerfile.pytorch-code and docker/Dockerfile.tf-code's
# previously-duplicated common portions
# (docs/superpowers/plans/2026-08-03-consolidate-images.md).
FROM docker.io/cschranz/gpu-jupyter:v1.10_cuda-12.9_ubuntu-24.04_slim AS base

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ENV PIP_ROOT_USER_ACTION=ignore

USER root

# Basic tooling + code-server + sudo
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    rm -f /etc/apt/apt.conf.d/docker-clean && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    build-essential \
    cmake \
    ninja-build \
    pkg-config \
    libopenblas-dev \
    libomp-dev \
    htop \
    tmux \
    openssh-client \
    gh \
    nodejs \
    npm \
    btop \
    openssh-server \
    sudo && \
    curl -fsSL https://code-server.dev/install.sh | sh && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

RUN usermod -aG sudo "${NB_USER}"

# Jupyter + UI + proxies -- union of pytorch-code's and tf-code's
# previously-separate (but near-identical) extension lists, so both
# variants can build FROM this image without losing anything.
RUN --mount=type=cache,target=/home/${NB_USER}/.cache/pip \
    pip install --upgrade \
    jupyterlab==4.5.7 \
    jupyterlab-git \
    nbgitpuller \
    jupyter-resource-usage \
    catppuccin-jupyterlab \
    jupyterlab-horizon-theme \
    jupyterlab-topbar-text \
    lckr-jupyterlab-variableinspector \
    jupyterlab-image-editor \
    jupyterlab-link-share \
    jupyterlab-spreadsheet-editor \
    jupyterlab-filesystem-access \
    jupyter-archive \
    jlab-enhanced-cell-toolbar \
    jupyterlab-favorites \
    jlab-enhanced-launcher \
    jupyter-sshd-proxy \
    jupyter-server-proxy \
    git+https://github.com/bjoernellens1/jupyter-code-server \
    jupyter-glances-proxy \
    git-credential-helpers \
    jupyterlab-nvdashboard \
    ipywidgets \
    jupyterlab-lsp \
    jupyterlab-code-formatter \
    "python-lsp-server[all]" \
    black \
    isort \
    ruff \
    notebook-intelligence && \
    npm cache clean --force && \
    rm -rf /opt/conda/share/jupyter/lab/staging

# Install nb_conda_kernels via conda
RUN (mamba install -y -c conda-forge nb_conda_kernels || \
    /opt/conda/bin/conda install -y -c conda-forge nb_conda_kernels) && \
    /opt/conda/bin/conda clean -afy

# Enable extensions
RUN    jupyter server extension enable --sys-prefix jupyter_remote_desktop_proxy || true && \
    jupyter server extension enable --sys-prefix jupyterlab_nvdashboard || true

# Copy pre-notebook hooks
COPY 00-prepare-readonly-home.sh /usr/local/bin/before-notebook.d/
COPY fix-permissions.sh /usr/local/bin/before-notebook.d/
RUN chmod +x /usr/local/bin/before-notebook.d/*.sh

# IPython config
RUN mkdir -p /root/.ipython/profile_default
COPY ipython_kernel_config.py /root/.ipython/profile_default/ipython_kernel_config.py

RUN chown -R ${NB_USER}:users /home/${NB_USER}

# Pre-init conda for NB_USER
RUN echo ". /opt/conda/etc/profile.d/conda.sh" >> /home/${NB_USER}/.bashrc && \
    echo "conda activate base" >> /home/${NB_USER}/.bashrc

RUN apt-get update && apt-get install -y jq && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

USER ${NB_USER}
COPY --chown=${NB_USER}:users install-copilot.sh /tmp/install-copilot.sh
RUN chmod +x /tmp/install-copilot.sh && /tmp/install-copilot.sh && rm /tmp/install-copilot.sh
USER root

RUN code-server --install-extension ms-python.python && \
    code-server --install-extension ms-toolsai.jupyter && \
    code-server --install-extension charliermarsh.ruff && \
    code-server --install-extension tamasfe.even-better-toml && \
    code-server --install-extension redhat.vscode-yaml && \
    code-server --install-extension ms-azuretools.vscode-docker && \
    code-server --install-extension mhutchie.git-graph

USER root
WORKDIR /home/${NB_USER}/work
```

- [ ] **Step 3: Run structural checks and confirm the two new base files are now found (even though variants aren't refactored yet)**

Run: `python3 docker/tests/structural_checks.py`
Expected: still exits 1 (variants not refactored yet), but the "Expected base Dockerfile ... not found yet" errors for `Dockerfile.base-cpu`/`Dockerfile.base-gpu` are gone from the output — confirms only the still-expected variant-refactor violations remain.

- [ ] **Step 4: Build `base-cpu` locally to confirm it's syntactically valid and completes (small image, safe per Global Constraints)**

Run: `cd docker && docker build -f Dockerfile.base-cpu -t cps-jupyter-notebook-base-cpu:test --secret id=root_password,src=/dev/null .`
Expected: build completes successfully. Do NOT attempt this for `Dockerfile.base-gpu` locally (CUDA base image, too large — verify its syntax only via `docker build --check` or by careful manual review, not a full build).

- [ ] **Step 5: Run functional checks against the locally-built base-cpu image**

Run: `sh docker/tests/run_functional_checks.sh cps-jupyter-notebook-base-cpu:test standard-cpu`
Expected: all checks pass (base-cpu should already satisfy every "applies to every variant" check in `functional_checks.sh`, since it's the not-yet-slimmed-down `standard-cpu` content).

- [ ] **Step 6: Commit**

```bash
git add docker/Dockerfile.base-cpu docker/Dockerfile.base-gpu
git commit -m "feat: add shared base-cpu and base-gpu images for the consolidation refactor"
```

---

### Task 3: Refactor `docker/Dockerfile` (standard-cpu) to build FROM `base-cpu`

**Files:**
- Modify: `docker/Dockerfile`

**Interfaces:**
- Consumes: `ghcr.io/mul-cps/cps-jupyter-notebook-base-cpu:latest` (published by Task 2's Dockerfile, once CI builds it — see Task 8).
- Produces: the exact same runtime content as before (this variant currently has NO unique content beyond what Task 2 already extracted into `base-cpu` — the entire file becomes a one-line `FROM`).

- [ ] **Step 1: Replace the full content of `docker/Dockerfile`**

```dockerfile
# docker/Dockerfile -- standard-cpu variant
#
# This variant has no content beyond the shared base -- see
# docker/Dockerfile.base-cpu and
# docs/superpowers/plans/2026-08-03-consolidate-images.md for what's
# included and why this file is intentionally this short.
FROM ghcr.io/mul-cps/cps-jupyter-notebook-base-cpu:latest
```

- [ ] **Step 2: Update `structural_checks.py`'s `CONSOLIDATED_VARIANTS` mapping if needed**

The mapping already expects `Dockerfile` -> `ghcr.io/mul-cps/cps-jupyter-notebook-base-cpu` from Task 1 — no change needed. Just re-run: `python3 docker/tests/structural_checks.py` and confirm the `Dockerfile` (standard-cpu) violations are gone from the output (base-gpu-dependent variants will still show as failing until their own tasks land).

- [ ] **Step 3: Commit**

```bash
git add docker/Dockerfile
git commit -m "refactor: build standard-cpu variant FROM the shared base-cpu image"
```

---

### Task 4: Refactor `docker/Dockerfile.pytorch-code` to build FROM `base-gpu`

**Files:**
- Modify: `docker/Dockerfile.pytorch-code`

**Interfaces:**
- Consumes: `ghcr.io/mul-cps/cps-jupyter-notebook-base-gpu:latest`.
- Produces: only the PyTorch-specific layer on top of the shared base.

- [ ] **Step 1: Replace the full content of `docker/Dockerfile.pytorch-code`**

```dockerfile
# docker/Dockerfile.pytorch-code -- pytorch-code variant
#
# Adds the PyTorch GPU stack on top of the shared base-gpu image. See
# docker/Dockerfile.base-gpu and
# docs/superpowers/plans/2026-08-03-consolidate-images.md.
FROM ghcr.io/mul-cps/cps-jupyter-notebook-base-gpu:latest

USER root

# PyTorch GPU stack -- separate pip call with CUDA 12.9 index
RUN --mount=type=cache,target=/home/${NB_USER}/.cache/pip \
    pip install --upgrade \
    "torch==2.11.*" \
    "torchvision==0.26.*" \
    "torchaudio==2.11.*" \
    --index-url https://download.pytorch.org/whl/cu129

# Vision / ML tooling
RUN --mount=type=cache,target=/home/${NB_USER}/.cache/pip \
    pip install --upgrade \
    transformers \
    datasets \
    accelerate \
    lightning \
    timm \
    opencv-python-headless \
    scikit-image \
    scikit-learn \
    pandas \
    matplotlib \
    seaborn

USER root
WORKDIR /home/${NB_USER}/work
```

- [ ] **Step 2: Run structural checks**

Run: `python3 docker/tests/structural_checks.py`
Expected: `Dockerfile.pytorch-code` violations gone.

- [ ] **Step 3: Commit**

```bash
git add docker/Dockerfile.pytorch-code
git commit -m "refactor: build pytorch-code variant FROM the shared base-gpu image"
```

---

### Task 5: Refactor `docker/Dockerfile.tf-code` to build FROM `base-gpu`

**Files:**
- Modify: `docker/Dockerfile.tf-code`

**Interfaces:**
- Consumes: `ghcr.io/mul-cps/cps-jupyter-notebook-base-gpu:latest`.
- Produces: only the TensorFlow-specific layer on top of the shared base.

- [ ] **Step 1: Replace the full content of `docker/Dockerfile.tf-code`**

```dockerfile
# docker/Dockerfile.tf-code -- tf-code variant
#
# Adds the TensorFlow GPU stack on top of the shared base-gpu image. See
# docker/Dockerfile.base-gpu and
# docs/superpowers/plans/2026-08-03-consolidate-images.md.
FROM ghcr.io/mul-cps/cps-jupyter-notebook-base-gpu:latest

USER root

# TensorFlow GPU stack (no addons)
RUN --mount=type=cache,target=/home/${NB_USER}/.cache/pip \
    pip install --upgrade \
    "tensorflow[and-cuda]==2.21.*" \
    tensorflow-datasets \
    keras \
    tf-keras \
    scikit-learn \
    pandas \
    seaborn \
    matplotlib

USER root
WORKDIR /home/${NB_USER}/work
```

- [ ] **Step 2: Run structural checks**

Run: `python3 docker/tests/structural_checks.py`
Expected: `Dockerfile.tf-code` violations gone.

- [ ] **Step 3: Commit**

```bash
git add docker/Dockerfile.tf-code
git commit -m "refactor: build tf-code variant FROM the shared base-gpu image"
```

---

### Task 6: Refactor `docker/Dockerfile.desktop-ros2` to chain off the `pytorch-code` image

**Files:**
- Modify: `docker/Dockerfile.desktop-ros2`

**Interfaces:**
- Consumes: `ghcr.io/mul-cps/cps-jupyter-notebook:latest-pytorch-code` (the REAL, already-consolidated, published pytorch-code variant image from Task 4 — not `base-gpu` directly, since this variant needs the full PyTorch stack that `pytorch-code` already provides, and reusing that published image as a real cached layer eliminates the current full duplicate PyTorch installation).
- Produces: the ROS2/desktop-specific layer only. The current file's own `jupyterlab==4.5.7`/`jupyter-remote-desktop-proxy`/extension bundle install and `torch`/`torchvision`/`torchaudio`/`transformers`/etc install are REMOVED since `pytorch-code` already provides all of that; `jupyter-remote-desktop-proxy` (the one package this variant needs that plain `pytorch-code` does NOT already have) is still installed here.

- [ ] **Step 1: Replace the full content of `docker/Dockerfile.desktop-ros2`**

Keep the existing 3-stage structure (`base` -> `extensions` -> `final`) exactly as-is for the code-server-extension-caching mechanism, but change stage `base`'s `FROM` and remove everything that `pytorch-code` already provides:

```dockerfile
# docker/Dockerfile.desktop-ros2
#
# Adds ROS 2 Jazzy desktop + VirtualGL/TurboVNC/XFCE4 on top of the
# already-published pytorch-code image (which already has the full
# PyTorch stack + shared JupyterLab/code-server bundle) instead of
# reinstalling PyTorch and the shared bundle from scratch. See
# docs/superpowers/plans/2026-08-03-consolidate-images.md.
# =========================
# Stage 0: base runtime
# =========================
FROM ghcr.io/mul-cps/cps-jupyter-notebook:latest-pytorch-code AS base

# Toggle optional heavy GUI apps (saves CI disk if disabled)
ARG INCLUDE_VSCODE_DESKTOP=0

SHELL ["/bin/bash", "-o", "pipefail", "-c"]
USER root
ENV DEBIAN_FRONTEND=noninteractive

# ---- Locale + base tooling (includes what we need for repos/keys)
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
        --mount=type=cache,target=/var/lib/apt,sharing=locked \
        set -eux; \
        rm -f /etc/apt/apt.conf.d/docker-clean; \
        apt-get update; \
        apt-get install -y --no-install-recommends \
            locales \
            gnupg2 \
            lsb-release \
            curl \
            ca-certificates; \
        locale-gen en_US en_US.UTF-8; \
        update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8; \
        rm -rf /var/lib/apt/lists/*

ENV LANG=en_US.UTF-8
ENV LC_ALL=en_US.UTF-8
ENV PIP_ROOT_USER_ACTION=ignore
ENV QT_QPA_PLATFORM=xcb

# ---- ROS 2 Jazzy repo
RUN set -eux; \
        curl -fsSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
            | tee /usr/share/keyrings/ros-archive-keyring.gpg >/dev/null; \
        echo "deb [signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu \
        $(. /etc/os-release && echo $UBUNTU_CODENAME) main" \
            > /etc/apt/sources.list.d/ros2.list

# ---- VirtualGL via .deb + EGL/GL userland deps
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
        --mount=type=cache,target=/var/lib/apt,sharing=locked \
        set -eux; \
        apt-get update; \
        apt-get install -y --no-install-recommends \
            wget \
            mesa-utils \
            libglvnd0 libegl1 libgl1 \
            libx11-6 libxext6 libxrender1 libxrandr2 libxi6 libxfixes3 \
            libxdamage1 libxinerama1 libxcursor1 libxcomposite1 \
            libsm6 libice6 libglib2.0-0; \
        wget -q -O /tmp/virtualgl.deb https://github.com/VirtualGL/virtualgl/releases/download/3.1.4/virtualgl_3.1.4_amd64.deb; \
        apt-get install -y /tmp/virtualgl.deb; \
        rm -f /tmp/virtualgl.deb; \
        rm -rf /var/lib/apt/lists/*

# ---- Desktop + noVNC + ROS + tooling
# NOTE: xorg removed (not needed for EGL mode; Xvnc provides desktop X server)
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
        --mount=type=cache,target=/var/lib/apt,sharing=locked \
        set -eux; \
        apt-get update; \
        apt-get install -y --no-install-recommends \
            dbus-x11 \
            xfce4 \
            xfce4-terminal \
            xubuntu-icon-theme \
            novnc \
            websockify \
            supervisor \
            pulseaudio \
            git \
            wget \
            build-essential \
            cmake \
            ninja-build \
            pkg-config \
            libopenblas-dev \
            libomp-dev \
            htop \
            tmux \
            openssh-client \
            openssh-server \
            sudo \
            jq \
            ros-jazzy-desktop \
            ros-jazzy-rmw-cyclonedds-cpp \
            python3-colcon-common-extensions \
            python3-vcstool \
            python3-rosdep; \
        rm -rf /var/lib/apt/lists/*

# ---- VS Code Desktop repo + optional install (skipped by default to save space)
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
        --mount=type=cache,target=/var/lib/apt,sharing=locked \
        set -eux; \
        curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor > /usr/share/keyrings/packages.microsoft.gpg; \
        echo "deb [arch=amd64 signed-by=/usr/share/keyrings/packages.microsoft.gpg] https://packages.microsoft.com/repos/code stable main" \
            > /etc/apt/sources.list.d/vscode.list; \
        if [ "${INCLUDE_VSCODE_DESKTOP}" = "1" ]; then \
          apt-get update; \
          apt-get install -y --no-install-recommends \
            code \
            terminator \
            firefox \
            vlc \
            thunar-archive-plugin \
            evince; \
        fi; \
        rm -rf /var/lib/apt/lists/*

# ---- TurboVNC (kept as .deb; could also be from upstream apt, but this is fine)
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
        --mount=type=cache,target=/var/lib/apt,sharing=locked \
        set -eux; \
        apt-get update; \
        apt-get install -y --no-install-recommends wget; \
        wget -q -O /tmp/turbovnc.deb https://github.com/TurboVNC/turbovnc/releases/download/3.3/turbovnc_3.3_amd64.deb; \
        apt-get install -y /tmp/turbovnc.deb; \
        rm -f /tmp/turbovnc.deb; \
        ln -sf /opt/TurboVNC/bin/vncserver /usr/local/bin/vncserver; \
        ln -sf /opt/TurboVNC/bin/vncpasswd /usr/local/bin/vncpasswd; \
        ln -sf /opt/TurboVNC/bin/vncconnect /usr/local/bin/vncconnect; \
        ln -sf /opt/TurboVNC/bin/tvncconfig /usr/local/bin/tvncconfig; \
        printf '%s\n' '#!/bin/sh' 'exec /opt/TurboVNC/bin/Xvnc "$@"' > /usr/local/bin/Xvnc; \
        chmod +x /usr/local/bin/Xvnc; \
        apt-get remove -y tigervnc-standalone-server || true; \
        apt-get autoremove -y; \
        rm -rf /var/lib/apt/lists/*

# ---- ROS environment
RUN set -eux; \
        echo "source /opt/ros/jazzy/setup.bash" >> /etc/bash.bashrc; \
        echo "source /opt/ros/jazzy/setup.bash" >> /etc/skel/.bashrc; \
        echo "source /opt/ros/jazzy/setup.bash" >> /home/${NB_USER}/.bashrc || true

RUN set -eux; \
        rosdep init || true; \
        rosdep update || true

# ---- jupyter-remote-desktop-proxy: the one package this variant needs
# that pytorch-code (its new base) does not already provide.
RUN --mount=type=cache,target=/home/${NB_USER}/.cache/pip \
        set -eux; \
        pip install --upgrade jupyter-remote-desktop-proxy; \
        rm -rf /opt/conda/share/jupyter/lab/staging /root/.cache /home/${NB_USER}/.cache || true

# Enable server extensions
RUN set -eux; \
        jupyter server extension enable --sys-prefix jupyter_server_proxy || true; \
        jupyter server extension enable --sys-prefix jupyter_remote_desktop_proxy || true; \
        jupyter server extension enable --sys-prefix jupyterlab_nvdashboard || true

# ---- Auto-wrap VirtualGL EGL (users don't have to type vglrun)
RUN set -eux; \
        cat > /usr/local/bin/_vglwrap <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
if [[ -z "${DISPLAY:-}" ]]; then
    exec "$@"
fi
export VGL_DISPLAY="${VGL_DISPLAY:-egl}"
if [[ ! -e /dev/nvidia0 && -z "${NVIDIA_VISIBLE_DEVICES:-}" ]]; then
    exec "$@"
fi
exec vglrun -d "${VGL_DISPLAY}" "$@"
EOF
RUN chmod +x /usr/local/bin/_vglwrap

RUN set -eux; \
        for app in glxinfo glxgears blender gazebo rviz; do \
            if command -v "$app" >/dev/null 2>&1; then \
                real="$(command -v "$app")"; \
                printf '%s\n' '#!/usr/bin/env bash' "exec /usr/local/bin/_vglwrap \"$real\" \"\$@\"" > "/usr/local/bin/$app"; \
                chmod +x "/usr/local/bin/$app"; \
            fi; \
        done

RUN mkdir -p /usr/local/bin/before-notebook.d

RUN set -eux; \
        echo ". /opt/conda/etc/profile.d/conda.sh" >> /home/${NB_USER}/.bashrc; \
        echo "conda activate base" >> /home/${NB_USER}/.bashrc; \
        chown -R ${NB_USER}:users /home/${NB_USER}

WORKDIR /home/${NB_USER}/work


# =========================
# Stage 1: code-server extensions (build once, copy artifacts)
# =========================
FROM base AS extensions

USER root
RUN set -eux; \
        mkdir -p /opt/code-server-ext /opt/code-server-data; \
        chown -R ${NB_USER}:users /opt/code-server-ext /opt/code-server-data

USER ${NB_USER}

RUN set -eux; \
        code-server \
            --user-data-dir /opt/code-server-data \
            --extensions-dir /opt/code-server-ext \
            --install-extension ms-python.python; \
        code-server \
            --user-data-dir /opt/code-server-data \
            --extensions-dir /opt/code-server-ext \
            --install-extension ms-toolsai.jupyter; \
        code-server \
            --user-data-dir /opt/code-server-data \
            --extensions-dir /opt/code-server-ext \
            --install-extension charliermarsh.ruff; \
        code-server \
            --user-data-dir /opt/code-server-data \
            --extensions-dir /opt/code-server-ext \
            --install-extension tamasfe.even-better-toml; \
        code-server \
            --user-data-dir /opt/code-server-data \
            --extensions-dir /opt/code-server-ext \
            --install-extension redhat.vscode-yaml; \
        code-server \
            --user-data-dir /opt/code-server-data \
            --extensions-dir /opt/code-server-ext \
            --install-extension ms-azuretools.vscode-docker; \
        code-server \
            --user-data-dir /opt/code-server-data \
            --extensions-dir /opt/code-server-ext \
            --install-extension mhutchie.git-graph


# =========================
# Stage 2: final image (copy extension cache in)
# =========================
FROM base AS final

USER root
COPY --from=extensions /opt/code-server-ext /opt/code-server-ext
COPY --from=extensions /opt/code-server-data /opt/code-server-data

ENV CODE_SERVER_EXTENSIONS_DIR=/opt/code-server-ext
ENV CODE_SERVER_USER_DATA_DIR=/opt/code-server-data

COPY 00-prepare-readonly-home.sh /usr/local/bin/before-notebook.d/
COPY fix-permissions.sh /usr/local/bin/before-notebook.d/
RUN chmod +x /usr/local/bin/before-notebook.d/*.sh

RUN mkdir -p /root/.ipython/profile_default
COPY ipython_kernel_config.py /root/.ipython/profile_default/ipython_kernel_config.py

USER ${NB_USER}
COPY --chown=${NB_USER}:users install-copilot.sh /tmp/install-copilot.sh
RUN chmod +x /tmp/install-copilot.sh && /tmp/install-copilot.sh && rm /tmp/install-copilot.sh

USER root
RUN set -eux; \
    cat > /etc/profile.d/10-virtualgl-egl.sh <<'EOF'
export VGL_DISPLAY=${VGL_DISPLAY:-egl}
EOF

RUN set -eux; \
    echo 'export VGL_DISPLAY=${VGL_DISPLAY:-egl}' >> /etc/bash.bashrc
WORKDIR /home/${NB_USER}/work
```

Note: the `before-notebook.d` hooks, ipython config, and Copilot install are still re-run in stage `final` here (matching the ORIGINAL file's structure, which already did this in its own `final` stage even though `base` also had a hooks directory) — this is intentionally preserved as-is rather than "cleaned up" further, since removing it is out of scope for this plan (Global Constraints: no behavior changes beyond what's specified).

- [ ] **Step 2: Run structural checks**

Run: `python3 docker/tests/structural_checks.py`
Expected: `Dockerfile.desktop-ros2` violations gone.

- [ ] **Step 3: Commit**

```bash
git add docker/Dockerfile.desktop-ros2
git commit -m "refactor: build desktop-ros2 variant FROM the published pytorch-code image"
```

---

### Task 7: Refactor `docker/Dockerfile.comfyui` to chain off the `pytorch-code` image

**Files:**
- Modify: `docker/Dockerfile.comfyui`

**Interfaces:**
- Consumes: `ghcr.io/mul-cps/cps-jupyter-notebook:latest-pytorch-code`.
- Produces: only the ComfyUI-specific layer (clone ComfyUI + Manager, install their requirements, install `jupyter-comfyui-proxy`, password handling, hooks copy, `start-comfyui.sh`). The current file's own JupyterLab-extension-bundle install, code-server install, sudo setup, and PyTorch install are REMOVED since `pytorch-code` already provides them.

- [ ] **Step 1: Replace the full content of `docker/Dockerfile.comfyui`**

```dockerfile
# ComfyUI Jupyter Notebook Image
#
# Adds ComfyUI on top of the already-published pytorch-code image
# (which already has the full PyTorch stack + shared JupyterLab/
# code-server bundle) instead of reinstalling PyTorch and the shared
# bundle from scratch. See
# docs/superpowers/plans/2026-08-03-consolidate-images.md.
FROM ghcr.io/mul-cps/cps-jupyter-notebook:latest-pytorch-code AS base

USER root

# ComfyUI-specific system dependencies not already covered by base
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y \
  libgl1 \
  libglx-mesa0 \
  libglib2.0-0 \
  libsm6 \
  libxext6 \
  libxrender-dev \
  libgomp1 \
  && rm -rf /var/lib/apt/lists/*

USER jovyan

# Clone ComfyUI
WORKDIR /opt/comfyui
RUN git clone https://github.com/comfyanonymous/ComfyUI.git .

# Install ComfyUI dependencies (torch/torchvision/torchaudio already
# provided by the pytorch-code base -- no separate PyTorch install here)
RUN pip install --no-cache-dir -r requirements.txt

# Clone ComfyUI Manager into custom_nodes
WORKDIR /opt/comfyui/custom_nodes
RUN git clone https://github.com/ltdrdata/ComfyUI-Manager.git

# Install ComfyUI Manager dependencies
WORKDIR /opt/comfyui/custom_nodes/ComfyUI-Manager
RUN pip install --no-cache-dir -r requirements.txt

# Install jupyter-comfyui-proxy
COPY --chown=jovyan:users jupyter-comfyui-proxy /tmp/jupyter-comfyui-proxy
RUN pip install /tmp/jupyter-comfyui-proxy && \
  rm -rf /tmp/jupyter-comfyui-proxy

# Switch to root for permission changes and password setup
USER root

# Set proper permissions for ComfyUI directory
RUN chown -R jovyan:users /opt/comfyui

# Handle password configuration
RUN --mount=type=secret,id=root_password \
  if [ -f /run/secrets/root_password ] && [ -s /run/secrets/root_password ]; then \
  echo "${NB_USER}:$(cat /run/secrets/root_password)" | chpasswd ; \
  else \
  echo "INFO: /run/secrets/root_password missing or empty, skipping password change"; \
  fi

USER root

# Copy pre-notebook hooks (already present from base, but keep this
# explicit copy to match the pre-refactor file's own behavior exactly)
RUN mkdir -p /usr/local/bin/before-notebook.d
COPY 00-prepare-readonly-home.sh /usr/local/bin/before-notebook.d/
COPY fix-permissions.sh /usr/local/bin/before-notebook.d/
RUN chmod +x /usr/local/bin/before-notebook.d/*.sh

USER jovyan

WORKDIR /home/jovyan/work

# Copy ipython kernel config
RUN mkdir -p /home/jovyan/.ipython/profile_default
COPY ipython_kernel_config.py /home/jovyan/.ipython/profile_default/ipython_kernel_config.py

ENV COMFYUI_PATH=/opt/comfyui
ENV username=jovyan

# Create a startup script to launch ComfyUI in the background
COPY --chown=jovyan:users --chmod=755 start-comfyui.sh /opt/comfyui/start-comfyui.sh
```

- [ ] **Step 2: Run structural checks**

Run: `python3 docker/tests/structural_checks.py`
Expected: `Dockerfile.comfyui` violations gone. All 5 variants plus both base files should now pass, i.e. the script should print "All structural checks passed." and exit 0.

- [ ] **Step 3: Commit**

```bash
git add docker/Dockerfile.comfyui
git commit -m "refactor: build comfyui variant FROM the published pytorch-code image"
```

---

### Task 8: Update CI to build base images and pytorch-code before the images that depend on them

**Files:**
- Modify: `.github/workflows/docker-publish.yml`

**Interfaces:**
- Produces: a workflow where `base-cpu` and `base-gpu` build and push first (a new job), `pytorch-code` and `tf-code` build next (depend on `base-gpu`), and `standard-cpu`/`desktop-ros2`/`comfyui` build last (`standard-cpu` depends on `base-cpu`; `desktop-ros2`/`comfyui` depend on the just-published `pytorch-code`).

- [ ] **Step 1: Restructure the workflow into dependency-ordered jobs**

Replace the single `check-changes` + `build-and-push` matrix with three sequential stages. Read the current full file first (`.github/workflows/docker-publish.yml`) to preserve the exact `Free up disk space on runner` step, `docker/metadata-action` tag scheme, and `secrets:` block unchanged in every job — only the job/dependency structure and matrix contents change:

```yaml
name: Build & Publish ML Variants

on:
  push:
    branches: [ main ]
    tags:
      - "v*.*.*"
    paths:
      - 'docker/**'
      - '.github/workflows/docker-publish.yml'
  pull_request:
    branches: [ main ]
    paths:
      - 'docker/**'
      - '.github/workflows/docker-publish.yml'

env:
  IMAGE_NAME: cps-jupyter-notebook

jobs:
  build-bases:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
      id-token: write
    strategy:
      fail-fast: false
      matrix:
        base: [base-cpu, base-gpu]
    steps:
      - uses: actions/checkout@v4
      - name: Free up disk space on runner
        run: |
          echo "Initial disk usage:"; df -h
          sudo rm -rf /usr/local/lib/android || true
          sudo rm -rf /usr/share/dotnet || true
          sudo rm -rf /usr/share/swift || true
          sudo rm -rf /opt/ghc || true
          sudo rm -rf /usr/local/.ghtl || true
          sudo rm -rf /opt/hostedtoolcache/CodeQL || true
          sudo swapoff -a
          sudo rm -f /mnt/swapfile
          docker system prune -af || true
          docker builder prune -af || true
          echo "Disk usage after cleanup:"; df -h
      - uses: docker/setup-qemu-action@v3
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - name: Extract metadata (tags, labels)
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: |
            ghcr.io/${{ github.repository_owner }}/${{ env.IMAGE_NAME }}-${{ matrix.base }}
          tags: |
            type=raw,value=latest,enable=${{ startsWith(github.ref, 'refs/heads/main') }}
            type=ref,event=branch
            type=ref,event=tag
            type=sha
          labels: |
            org.opencontainers.image.source=${{ github.server_url }}/${{ github.repository }}
            org.opencontainers.image.revision=${{ github.sha }}
      - name: Build and push
        uses: docker/build-push-action@v6
        with:
          context: ./docker
          file: docker/Dockerfile.${{ matrix.base }}
          push: ${{ github.event_name != 'pull_request' }}
          platforms: linux/amd64
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          secrets: |
            "admin_password=${{ secrets.CPS_JUPYTER_ADMIN_PASSWORD }}"
            "root_password=${{ secrets.CPS_JUPYTER_ROOT_PASSWORD }}"
          cache-from: type=gha,scope=${{ matrix.base }}
          cache-to: type=gha,mode=max,scope=${{ matrix.base }}

  build-gpu-frameworks:
    needs: build-bases
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
      id-token: write
    strategy:
      fail-fast: false
      matrix:
        variant: [pytorch-code, tf-code]
    steps:
      - uses: actions/checkout@v4
      - name: Free up disk space on runner
        run: |
          sudo rm -rf /usr/local/lib/android || true
          sudo rm -rf /usr/share/dotnet || true
          sudo rm -rf /usr/share/swift || true
          sudo rm -rf /opt/ghc || true
          sudo rm -rf /usr/local/.ghtl || true
          sudo rm -rf /opt/hostedtoolcache/CodeQL || true
          sudo swapoff -a
          sudo rm -f /mnt/swapfile
          docker system prune -af || true
          docker builder prune -af || true
      - uses: docker/setup-qemu-action@v3
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - name: Extract metadata (tags, labels)
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: |
            ghcr.io/${{ github.repository_owner }}/${{ env.IMAGE_NAME }}
          tags: |
            type=raw,value=latest-${{ matrix.variant }},enable=${{ startsWith(github.ref, 'refs/heads/main') }}
            type=ref,event=branch,suffix=-${{ matrix.variant }}
            type=ref,event=tag,suffix=-${{ matrix.variant }}
            type=sha,suffix=-${{ matrix.variant }}
          labels: |
            org.opencontainers.image.source=${{ github.server_url }}/${{ github.repository }}
            org.opencontainers.image.revision=${{ github.sha }}
      - name: Build and push
        uses: docker/build-push-action@v6
        with:
          context: ./docker
          file: docker/Dockerfile.${{ matrix.variant }}
          push: ${{ github.event_name != 'pull_request' }}
          platforms: linux/amd64
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          secrets: |
            "admin_password=${{ secrets.CPS_JUPYTER_ADMIN_PASSWORD }}"
            "root_password=${{ secrets.CPS_JUPYTER_ROOT_PASSWORD }}"
          cache-from: type=gha,scope=${{ matrix.variant }}
          cache-to: type=gha,mode=max,scope=${{ matrix.variant }}
      - name: Generate Job Summary
        if: always()
        run: |
          echo "### Build Summary :rocket:" >> $GITHUB_STEP_SUMMARY
          echo "| Variant | Dockerfile | Tags |" >> $GITHUB_STEP_SUMMARY
          echo "| :--- | :--- | :--- |" >> $GITHUB_STEP_SUMMARY
          echo "| ${{ matrix.variant }} | docker/Dockerfile.${{ matrix.variant }} | ${{ steps.meta.outputs.tags }} |" >> $GITHUB_STEP_SUMMARY

  build-dependents:
    needs: build-gpu-frameworks
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
      id-token: write
    strategy:
      fail-fast: false
      matrix:
        include:
          - name: standard-cpu
            dockerfile: docker/Dockerfile
            suffix: standard-cpu
          - name: desktop-ros2
            dockerfile: docker/Dockerfile.desktop-ros2
            suffix: desktop-ros2
          - name: comfyui
            dockerfile: docker/Dockerfile.comfyui
            suffix: comfyui
    steps:
      - uses: actions/checkout@v4
      - name: Free up disk space on runner
        run: |
          sudo rm -rf /usr/local/lib/android || true
          sudo rm -rf /usr/share/dotnet || true
          sudo rm -rf /usr/share/swift || true
          sudo rm -rf /opt/ghc || true
          sudo rm -rf /usr/local/.ghtl || true
          sudo rm -rf /opt/hostedtoolcache/CodeQL || true
          sudo swapoff -a
          sudo rm -f /mnt/swapfile
          docker system prune -af || true
          docker builder prune -af || true
      - uses: docker/setup-qemu-action@v3
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - name: Extract metadata (tags, labels)
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: |
            ghcr.io/${{ github.repository_owner }}/${{ env.IMAGE_NAME }}
          tags: |
            type=raw,value=latest-${{ matrix.suffix }},enable=${{ startsWith(github.ref, 'refs/heads/main') }}
            type=ref,event=branch,suffix=-${{ matrix.suffix }}
            type=ref,event=tag,suffix=-${{ matrix.suffix }}
            type=sha,suffix=-${{ matrix.suffix }}
          labels: |
            org.opencontainers.image.source=${{ github.server_url }}/${{ github.repository }}
            org.opencontainers.image.revision=${{ github.sha }}
      - name: Build and push
        uses: docker/build-push-action@v6
        with:
          context: ./docker
          file: ${{ matrix.dockerfile }}
          push: ${{ github.event_name != 'pull_request' }}
          platforms: linux/amd64
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          secrets: |
            "admin_password=${{ secrets.CPS_JUPYTER_ADMIN_PASSWORD }}"
            "root_password=${{ secrets.CPS_JUPYTER_ROOT_PASSWORD }}"
          cache-from: type=gha,scope=${{ matrix.suffix }}
          cache-to: type=gha,mode=max,scope=${{ matrix.suffix }}
      - name: Generate Job Summary
        if: always()
        run: |
          echo "### Build Summary :rocket:" >> $GITHUB_STEP_SUMMARY
          echo "| Variant | Dockerfile | Tags |" >> $GITHUB_STEP_SUMMARY
          echo "| :--- | :--- | :--- |" >> $GITHUB_STEP_SUMMARY
          echo "| ${{ matrix.name }} | ${{ matrix.dockerfile }} | ${{ steps.meta.outputs.tags }} |" >> $GITHUB_STEP_SUMMARY
```

Note: this removes the previous `check-changes`/`paths-filter` dynamic matrix (which only rebuilt what changed) in favor of always building everything on every push to `docker/**`. This is an intentional, acceptable trade-off flagged here rather than silently applied: with the new dependency chain, a change to `base-gpu` must always cascade to rebuild `pytorch-code`/`tf-code` and then `desktop-ros2`/`comfyui` anyway, so partial-matrix logic would need to become dependency-aware (significantly more complex) to still be correct. If the human reviewing this plan wants the partial-rebuild optimization preserved, that's a valid follow-up, not something to silently attempt within this task.

- [ ] **Step 2: Validate the YAML is well-formed**

Run: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/docker-publish.yml'))" && echo YAML_OK`

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/docker-publish.yml
git commit -m "ci: build base images and pytorch-code before their dependent variants"
```

---

### Task 9: Battle-test — trigger a real CI build, verify functional parity and measure real size reduction

**Files:**
- None modified (verification-only task). May create a scratch results file, e.g. `docs/superpowers/plans/2026-08-03-consolidate-images-results.md`, to record findings.

**Interfaces:**
- Consumes: the branch created by Tasks 1-8 (all committed), pushed to GitHub; the real GitHub Actions run it triggers; the real images it publishes to `ghcr.io/mul-cps/cps-jupyter-notebook*`.

- [ ] **Step 1: Push the branch and open a PR (or push directly if working on a branch that already targets `main` per the human's repo workflow) to trigger the new CI workflow**

Run: `git push -u origin <branch-name>` (use whatever branch this plan's tasks were executed on)
Then trigger the workflow (it runs automatically on push to a path matching `docker/**`, or via `gh workflow run docker-publish.yml` if the branch isn't `main` and the workflow needs a manual dispatch — check the `on:` triggers in the now-modified file first).

- [ ] **Step 2: Watch the run to completion**

Run: `gh run watch` (or `gh run list --workflow=docker-publish.yml` then `gh run watch <run-id>`)
Expected: `build-bases` completes first (2 jobs: base-cpu, base-gpu), then `build-gpu-frameworks` (2 jobs: pytorch-code, tf-code), then `build-dependents` (3 jobs: standard-cpu, desktop-ros2, comfyui). All 7 jobs succeed. If any job fails, read its logs, determine whether the failure is a real regression from this refactor (fix and re-push) or a pre-existing flake unrelated to this plan (note it, don't silently work around it) — do not mark this task complete with a red CI run.

- [ ] **Step 3: Pull each real published image and run the functional test suite against it**

For each variant, run (adjust `<tag>` to whatever this branch's `docker/metadata-action` produced, e.g. a `sha-` or branch-ref tag since `latest-*` only applies on `main`):

```bash
sh docker/tests/run_functional_checks.sh ghcr.io/mul-cps/cps-jupyter-notebook:<branch-tag>-standard-cpu standard-cpu
sh docker/tests/run_functional_checks.sh ghcr.io/mul-cps/cps-jupyter-notebook:<branch-tag>-pytorch-code pytorch-code
sh docker/tests/run_functional_checks.sh ghcr.io/mul-cps/cps-jupyter-notebook:<branch-tag>-tf-code tf-code
sh docker/tests/run_functional_checks.sh ghcr.io/mul-cps/cps-jupyter-notebook:<branch-tag>-desktop-ros2 desktop-ros2
sh docker/tests/run_functional_checks.sh ghcr.io/mul-cps/cps-jupyter-notebook:<branch-tag>-comfyui comfyui
```

Expected: `RESULT: all checks PASSED` for every variant. This IS allowed to pull large images on this machine (unlike `docker build`, a `docker pull` + `docker run` of an already-built image does not require the multi-GB build cache/context that made local building unsafe) — but immediately `docker rmi` each image after its test completes (the script's `docker rm -f` on the container doesn't remove the image layers) to avoid accumulating multiple 10-37GB images on the 77GB-free local disk at once. Test one variant at a time, not in parallel.

- [ ] **Step 4: Measure real image sizes and compare against `size_budgets.yaml`**

For each variant, run: `docker image inspect ghcr.io/mul-cps/cps-jupyter-notebook:<branch-tag>-<variant> --format '{{.Size}}'` immediately after that variant's functional test (before `docker rmi`ing it), and compare against the corresponding `max_bytes` in `docker/tests/size_budgets.yaml`. Also compare against the ORIGINAL pre-refactor sizes where known (pytorch-code ~17.6GB, desktop-ros2-xpra ~19-37GB per `docs/superpowers/specs/2026-07-24-spegel-image-mirroring-design.md` in the `cps-gpu-cluster` repo).

- [ ] **Step 5: Write up the results**

Create `docs/superpowers/plans/2026-08-03-consolidate-images-results.md` with: a table of before/after sizes per variant (before = documented/observed pre-refactor size where known, "not previously measured" otherwise; after = real size measured in Step 4), confirmation that every functional check passed for every variant, and the actual total registry storage delta (sum of all `after` sizes vs. sum of all `before` sizes, accounting for the fact that shared layers across variants are stored ONCE in the registry, not once per variant — note this explicitly since it's the main source of the real savings and isn't visible from a single image's reported `.Size` alone).

- [ ] **Step 6: Commit the results doc**

```bash
git add docs/superpowers/plans/2026-08-03-consolidate-images-results.md
git commit -m "docs: record image consolidation battle-test results"
```

---

### Task 10 (separate repo — cps-gpu-cluster): fix `prePuller.extraImages` gaps

**Files:**
- Modify: `/home/bjoern/git/cps-gpu-cluster/cluster-maintenance/clusters/cit-cps-gpu/user/jupyter/jupyterhub/values.yaml`

**Interfaces:**
- Produces: `prePuller.extraImages` includes all 7 currently-live profile image tags (adds the two currently-missing ones: `latest-desktop-ros2-xpra` and `main-comfyui`), so every profile is pre-pulled on cluster nodes instead of cold-pulling on first spawn.

This task is independent of Tasks 1-9 (different repo, no dependency) and can be done at any point, including in parallel. It is listed last only because it's a much smaller, unrelated fix bundled into this same plan per the user's request to "bring all the used jupyterhub images together."

- [ ] **Step 1: Read the current `prePuller.extraImages` block**

Run: `grep -n "prePuller" -A25 /home/bjoern/git/cps-gpu-cluster/cluster-maintenance/clusters/cit-cps-gpu/user/jupyter/jupyterhub/values.yaml`

- [ ] **Step 2: Add the two missing entries**

Add two new entries to the `prePuller.extraImages` map (matching the existing map's key style, e.g. `cps-desktop-ros2-xpra` and `cps-comfyui`) pointing at `ghcr.io/mul-cps/cps-jupyter-notebook:latest-desktop-ros2-xpra` and `ghcr.io/mul-cps/cps-jupyter-notebook:main-comfyui` respectively — read the exact existing map syntax first (Step 1's output) and match it exactly; do not guess the key/value structure.

**Known open question, flag rather than silently resolve:** the companion research found no `Dockerfile.desktop-ros2-xpra` (or any Xpra-specific Dockerfile) anywhere in the `cps-jupyter-notebook` repo, yet `latest-desktop-ros2-xpra` is a real, currently-referenced tag (`gpu-desktop-xpra` profile in `cps-gpu-cluster`). Before adding this prePuller entry, confirm the tag actually exists and is pullable (`gh api "/orgs/mul-cps/packages/container/cps-jupyter-notebook/versions" --jq '.[] | select(.metadata.container.tags[] | contains("xpra"))'`) and briefly note in the commit message how it's actually built (e.g. a manual/local build never committed to CI, or a build step this investigation missed) — do not silently assume it's fine without checking, since this same gap likely means Tasks 1-9's refactor doesn't cover however this tag actually gets built either.

- [ ] **Step 3: Verify YAML validity**

Run: `python3 -c "import yaml; yaml.safe_load(open('cluster-maintenance/clusters/cit-cps-gpu/user/jupyter/jupyterhub/values.yaml'))" && echo YAML_OK` (from the `cps-gpu-cluster` repo root)

- [ ] **Step 4: Commit**

```bash
git add cluster-maintenance/clusters/cit-cps-gpu/user/jupyter/jupyterhub/values.yaml
git commit -m "fix(jupyterhub): pre-pull the desktop-xpra and comfyui profile images too

prePuller.extraImages was missing latest-desktop-ros2-xpra and
main-comfyui, meaning those two profiles always cold-pulled a multi-GB
image on a node's first spawn instead of having it pre-pulled like
every other profile."
```

Per this repo's CLAUDE.md convention, this change takes effect only after Fleet syncs from git — do not apply it by hand.
