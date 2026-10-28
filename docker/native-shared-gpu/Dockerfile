# Experimental native shared-GPU image layer. The external build context
# `compute-wheel` and `lab-wheel` must each contain their reviewed wheel.
# The default base is the image used in the GPU2 per-Pod MPS feasibility test.
ARG BASE_IMAGE=ghcr.io/mul-cps/cps-jupyter-notebook@sha256:5427088986bc06ad0713875d1aa2f31439f0bd1fbe6099d4669570fcf3e85be4
FROM ${BASE_IMAGE}

USER root
ARG CPS_COMPUTE_WHEEL_SHA256
ARG CPS_LAB_WHEEL_SHA256
COPY --from=compute-wheel / /tmp/cps-compute-wheel/
COPY --from=lab-wheel / /tmp/cps-compute-lab-wheel/
RUN set -eu; \
    set -- /tmp/cps-compute-wheel/cps_compute-*.whl; \
    [ "$#" -eq 1 ] && [ -f "$1" ]; \
    echo "$CPS_COMPUTE_WHEEL_SHA256  $1" | sha256sum -c -; \
    python -m pip install --no-index --no-deps --force-reinstall "$1"; \
    set -- /tmp/cps-compute-lab-wheel/cps_compute_jupyterlab-*.whl; \
    [ "$#" -eq 1 ] && [ -f "$1" ]; \
    echo "$CPS_LAB_WHEEL_SHA256  $1" | sha256sum -c -; \
    python -m pip install --no-index --no-deps --force-reinstall "$1"; \
    test -x /opt/conda/bin/cps-mps-v2-exec; \
    env -u CPS_NATIVE_MPS_MODE /opt/conda/bin/cps-mps-v2-exec -- /bin/true; \
    rm -rf /tmp/cps-compute-wheel /tmp/cps-compute-lab-wheel; \
    install -d -o root -g root -m 0755 /etc/cps-compute
COPY mps-v2.json /etc/cps-compute/mps-v2.json
RUN chown root:root /etc/cps-compute/mps-v2.json && chmod 0644 /etc/cps-compute/mps-v2.json
USER ${NB_UID}
