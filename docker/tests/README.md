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
