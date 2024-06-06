#from jupyter/minimal-notebook:lab-3.6.3 as base
#from jupyter/datascience-notebook:lab-3.6.3 as base

from quay.io/jupyter/datascience-notebook:lab-4.2.1 as base

RUN pip install --upgrade jupyterlab-git \
    jupyterlab-lsp \
    'python-lsp-server[all]' \ 
    nbgitpuller \
    git-credential-helpers && \
    # R -e 'install.packages("languageserver")' && \
    npm cache clean --force && \
    rm -rf $CONDA_DIR/share/jupyter/lab/staging

USER root
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install \
    gh \
    && rm -rf /var/lib/apt/lists/*

USER jovyan
ENV GIT_SSL_NO_VERIFY="false"
WORKDIR /home/jovyan/work
COPY ipython_kernel_config.py /root/.ipython/profile_default/ipython_kernel_config.py
