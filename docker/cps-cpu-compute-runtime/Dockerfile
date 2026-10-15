# Preserve d75 runtime, SDK, scientific packages and all Hub/RTC configuration.
ARG BASE_IMAGE=ghcr.io/mul-cps/cps-jupyter-notebook@sha256:d75d54d9b2b3b1b497e577124a30ca4c82993dd8458550a0b1fa73c37159b64f
FROM ${BASE_IMAGE}
USER root
RUN --mount=type=bind,source=wheelhouse,target=/tmp/compute-wheelhouse,ro \
    python -m pip uninstall -y cps-compute-jupyterlab && \
    python -m pip install --no-cache-dir --no-index --no-deps --require-hashes \
      --find-links=/tmp/compute-wheelhouse -r /tmp/compute-wheelhouse/install.lock && \
    python -m pip check
USER 1000
# Keep inherited /home/jovyan/work, environment, command and entrypoint.
