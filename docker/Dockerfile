from quay.io/jupyter/datascience-notebook:lab-4.2.1 as base

ENV PIP_ROOT_USER_ACTION=ignore

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade \
    jupyterlab-git \
    nbgitpuller \
    jupyter-resource-usage \
    catppuccin-jupyterlab \
    jupyterlab-horizon-theme \
    jupyter-sshd-proxy \
    jupyter-server-proxy \
    git+https://github.com/bjoernellens1/jupyter-code-server \
    jupyter-glances-proxy \
    git-credential-helpers && \
    npm cache clean --force && \
    rm -rf $CONDA_DIR/share/jupyter/lab/staging

# nvidia dashboard extension
#RUN conda install -c rapidsai-nightly -c conda-forge jupyterlab-nvdashboard

USER root
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    rm -f /etc/apt/apt.conf.d/docker-clean && \
    apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y \
    --no-install-recommends \
    gh \
    nodejs \
    npm \
    jq \
    btop \
    openssh-server \
    && curl -fsSL https://code-server.dev/install.sh | sh \
    && rm -rf /var/lib/apt/lists/*

RUN usermod -aG sudo jovyan

ENV username=jovyan
# ENV password=jovyan

# RUN adduser --gecos "" --disabled-password $username
# from: https://docs.docker.com/build/ci/github-actions/secrets/#secret-mounts
# RUN --mount=type=secret,id=root_password,env=ROOT_PASSWORD echo "${username}:${ROOT_PASSWORD}" | chpasswd
RUN --mount=type=secret,id=root_password \
    if [ -f /run/secrets/root_password ] && [ -s /run/secrets/root_password ]; then \
    echo "${NB_USER}:$(cat /run/secrets/root_password)" | chpasswd ; \
    else \
    echo "INFO: /run/secrets/root_password missing or empty, skipping password change"; \
    fi

# enable passwordless sudo
# RUN echo 'jovyan ALL=(ALL) NOPASSWD: ALL' >> /etc/sudoers

RUN chown -R jovyan:users /home/jovyan

# Copy permission fix script
COPY fix-permissions.sh /usr/local/bin/before-notebook.d/
RUN chmod +x /usr/local/bin/before-notebook.d/fix-permissions.sh

USER jovyan
#ENV GIT_SSL_NO_VERIFY="false"
WORKDIR /home/jovyan/work
COPY ipython_kernel_config.py /root/.ipython/profile_default/ipython_kernel_config.py

# Install Copilot
# Install Copilot
RUN curl -fsSL https://raw.githubusercontent.com/sunpix/howto-install-copilot-in-code-server/refs/heads/main/install-copilot.sh | bash

# Install VS Code extensions
RUN code-server --install-extension ms-python.python && \
    code-server --install-extension ms-toolsai.jupyter && \
    code-server --install-extension charliermarsh.ruff && \
    code-server --install-extension tamasfe.even-better-toml && \
    code-server --install-extension redhat.vscode-yaml && \
    code-server --install-extension ms-azuretools.vscode-docker && \
    code-server --install-extension mhutchie.git-graph

# Switch to root to allow fixing permissions on startup
USER root
WORKDIR /home/jovyan/work
