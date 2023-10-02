from jupyter/minimal-notebook:lab-3.6.3 as base
RUN jupyter labextension install @jupyterlab/git@^0.5.0 && \
    npm cache clean --force && \
    rm -rf $CONDA_DIR/share/jupyter/lab/staging
