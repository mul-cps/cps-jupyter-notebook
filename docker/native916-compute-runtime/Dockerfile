# Candidate only: preserve the exact qualified native GPU runtime and all features.
FROM ghcr.io/mul-cps/cps-jupyter-notebook@sha256:9167861058c1364c58d1c2fca0d6f536c3ffb53a33800dcdb9a1560f14ca4dc0
USER root
RUN --mount=type=bind,source=wheelhouse,target=/tmp/compute-wheelhouse,ro \
    python -m pip uninstall -y cps-compute cps-compute-jupyterlab && \
    python -m pip install --no-cache-dir --no-index --no-deps --require-hashes \
      --find-links=/tmp/compute-wheelhouse -r /tmp/compute-wheelhouse/install.lock && \
    python -m pip check
USER 1000
# Inherit /workspace, native startup, entrypoint, command and environment unchanged.
