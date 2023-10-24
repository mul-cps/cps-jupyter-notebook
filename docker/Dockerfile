from jupyter/minimal-notebook:lab-3.6.3 as base
RUN pip install --upgrade "jupyterlab<4" jupyterlab-git \
    npm cache clean --force && \
    rm -rf $CONDA_DIR/share/jupyter/lab/staging

USER root
RUN sudo apt-get update && DEBIAN_FRONTEND=noninteractive sudo apt-get install \
    gh \
    && sudo rm -rf /var/lib/apt/lists/*

USER jovyan
ENV GIT_SSL_NO_VERIFY="false"
