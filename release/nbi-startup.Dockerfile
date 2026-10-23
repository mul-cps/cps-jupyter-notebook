# Release-tooling candidate overlay; promote through the normal image/policy handover.
ARG BASE_IMAGE=ghcr.io/mul-cps/cps-jupyter-notebook@sha256:fb9872bf71bfee402807c4f0e9adc92c49740ec30fa4a6a4261fa2ae18d32a45
FROM ${BASE_IMAGE}
USER root
COPY notebook_intelligence-4.6.0+cps.2-py3-none-any.whl qualify_nbi_lazy_client.py /tmp/cps-nbi-startup/
RUN echo 'bef15b74370cfd7ddc55fc9034d105e6c21e4b6bfc4e39d7b7a6edc638a0b71e  /tmp/cps-nbi-startup/notebook_intelligence-4.6.0+cps.2-py3-none-any.whl' | sha256sum -c - && \
    python -m pip install --no-index --no-deps --no-cache-dir --force-reinstall \
      /tmp/cps-nbi-startup/notebook_intelligence-4.6.0+cps.2-py3-none-any.whl && \
    python -m pip check && \
    JUPYTER_CONFIG_DIR=/tmp/cps-nbi-startup/config python -B /tmp/cps-nbi-startup/qualify_nbi_lazy_client.py && \
    rm -rf /tmp/cps-nbi-startup
USER 1000
