#from jupyter/minimal-notebook:lab-3.6.3 as base
#from jupyter/datascience-notebook:lab-3.6.3 as base

from quay.io/jupyter/datascience-notebook:lab-4.2.1 as base

RUN pip install --upgrade jupyterlab-git \
    jupyterlab-lsp \
    'python-lsp-server[all]' \ 
    nbgitpuller \
    jupyter-resource-usage \
    catppuccin-jupyterlab \
    dask-labextension \
    git-credential-helpers && \
    # R -e 'install.packages("languageserver")' && \
    npm cache clean --force && \
    rm -rf $CONDA_DIR/share/jupyter/lab/staging

# install all language servers (additional npm required ones)
# RUN jlpm add --dev  \
#     bash-language-server \
#     dockerfile-language-server-nodejs \
#     pyright \
#     sql-language-server \
#     typescript-language-server \
#     unified-language-server \
#     vscode-css-languageserver-bin \
#     vscode-html-languageserver-bin \
#     vscode-json-languageserver-bin \
#     yaml-language-server

# nvidia dashboard extension
RUN conda install -c rapidsai-nightly -c conda-forge jupyterlab-nvdashboard

USER root
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y \
    gh \
    nodejs \
    && rm -rf /var/lib/apt/lists/*

RUN usermod -aG sudo jovyan

ENV username=jovyan
ENV password=jovyan

# RUN adduser --gecos "" --disabled-password $username
RUN echo "${username}:${password}" | chpasswd

# enable passwordless sudo
RUN echo 'jovyan ALL=(ALL) NOPASSWD: ALL' >> /etc/sudoers

USER jovyan
#ENV GIT_SSL_NO_VERIFY="false"
WORKDIR /home/jovyan/work
COPY ipython_kernel_config.py /root/.ipython/profile_default/ipython_kernel_config.py
