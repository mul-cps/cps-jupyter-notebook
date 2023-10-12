from jupyter/minimal-notebook:lab-3.6.3 as base
RUN pip install --upgrade "jupyterlab<4" jupyterlab-git \
    npm cache clean --force && \
    rm -rf $CONDA_DIR/share/jupyter/lab/staging

ENV GIT_SSL_NO_VERIFY="false"
