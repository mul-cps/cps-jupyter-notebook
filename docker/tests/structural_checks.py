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

    # If the FROM line references a build ARG (e.g. `${BASE_IMAGE}` or
    # `$BASE_IMAGE`), resolve it to that ARG's default value by looking
    # for a preceding `ARG <NAME>=<value>` line, and compare that value
    # instead of the raw `${...}` token.
    var_match = re.match(r"^\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?$", first)
    if var_match:
        var_name = var_match.group(1)
        arg_match = re.search(
            rf"^ARG\s+{re.escape(var_name)}=(\S+)", text, re.MULTILINE
        )
        if not arg_match:
            errors.append(
                f"{path.name}: first FROM references ${{{var_name}}} but no "
                f"'ARG {var_name}=<value>' default was found in the file"
            )
            return
        first = arg_match.group(1)

    # If expected_base has no tag (no ':' in the last path segment after '/'),
    # strip any tag from first before comparing. This allows e.g.
    # 'ghcr.io/mul-cps/cps-jupyter-notebook-base-cpu:latest' to match
    # an expectation of 'ghcr.io/mul-cps/cps-jupyter-notebook-base-cpu'.
    # If expected_base DOES include a tag (e.g. 'latest-pytorch-code'),
    # require exact matching (both sides already have tags).
    last_segment_expected = expected_base.rsplit("/", 1)[-1]
    if ":" not in last_segment_expected:
        # expected_base has no tag, so strip tag from first before comparing
        first_to_compare = first.rsplit(":", 1)[0] if ":" in first else first
    else:
        # expected_base has a tag, so require exact match
        first_to_compare = first

    if first_to_compare != expected_base:
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
        if re.search(r"(^|\s)pip install\b", line):
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
