from quay.io/jupyter/datascience-notebook:lab-4.2.1 as base

RUN pip install --upgrade \
    jupyterlab-git \
    # jupyterlab-lsp \
    # 'python-lsp-server[all]' \ 
    nbgitpuller \
    jupyter-resource-usage \
    catppuccin-jupyterlab \
    jupyterlab-horizon-theme \
    #dask-labextension \
    jupyter-sshd-proxy \
    jupyter-server-proxy \
    #git+https://gitlab.com/idris-cnrs/jupyter/jupyter-proxy-apps/jupyter-code-server-proxy.git \
    #jupyter-code-server \
    git+https://github.com/bjoernellens1/jupyter-code-server \
    jupyter-glances-proxy \
    git-credential-helpers && \
    npm cache clean --force && \
    rm -rf $CONDA_DIR/share/jupyter/lab/staging

# nvidia dashboard extension
#RUN conda install -c rapidsai-nightly -c conda-forge jupyterlab-nvdashboard

# enable selection of environments that are installed later
# from https://discourse.jupyter.org/t/multiple-conda-environments/22530/2
#RUN conda install -n base nb_conda_kernels

USER root
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y \
    gh \
    nodejs \
    btop \
    openssh-server \
    && curl -fsSL https://code-server.dev/install.sh | sh \
    && rm -rf /var/lib/apt/lists/*

RUN usermod -aG sudo jovyan

ENV username=jovyan
# ENV password=jovyan

# RUN adduser --gecos "" --disabled-password $username
# from: https://docs.docker.com/build/ci/github-actions/secrets/#secret-mounts
RUN --mount=type=secret,id=root_password,env=ROOT_PASSWORD echo "${username}:${ROOT_PASSWORD}" | chpasswd

# enable passwordless sudo
# RUN echo 'jovyan ALL=(ALL) NOPASSWD: ALL' >> /etc/sudoers

USER jovyan
#ENV GIT_SSL_NO_VERIFY="false"
WORKDIR /home/jovyan/work
COPY ipython_kernel_config.py /root/.ipython/profile_default/ipython_kernel_config.py
