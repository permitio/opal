# BUILD STAGE ---------------------------------------
# split this stage to save time and reduce image size
# ---------------------------------------------------
FROM python:3.10-bookworm AS build-stage
# from now on, work in the /app directory
WORKDIR /app/
# Layer dependency install (for caching)
COPY ./packages/requires.txt ./base_requires.txt
COPY ./packages/opal-common/requires.txt ./common_requires.txt
COPY ./packages/opal-client/requires.txt ./client_requires.txt
COPY ./packages/opal-server/requires.txt ./server_requires.txt
# install python deps
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r ./base_requires.txt -r ./common_requires.txt -r ./client_requires.txt -r ./server_requires.txt

# COMMON IMAGE --------------------------------------
# ---------------------------------------------------
FROM python:3.10-slim-bookworm AS common

# copy libraries from build stage (This won't copy redundant libraries we used in build-stage)
# also remove the default python site-packages that has older versions of packages that won't be overridden
RUN rm -r /usr/local/lib/python3.10/site-packages
COPY --from=build-stage /usr/local /usr/local

# Add non-root user (with home dir at /opal)
RUN useradd -m -b / -s /bin/bash opal
WORKDIR /opal

# copy wait-for script (create link at old path to maintain backward compatibility)
COPY scripts/wait-for.sh .
RUN chmod +x ./wait-for.sh
RUN ln -s /opal/wait-for.sh /usr/wait-for.sh

# netcat (nc) is used by the wait-for.sh script
RUN apt-get update && apt-get install -y netcat-traditional jq wget && apt-get clean

# copy startup script (create link at old path to maintain backward compatibility)
COPY ./scripts/start.sh .
RUN chmod +x ./start.sh
RUN ln -s /opal/start.sh /start.sh
# copy gunicorn_config
COPY ./scripts/gunicorn_conf.py .
# copy app code

COPY ./README.md .
COPY ./packages ./packages/
# install the opal-common package
RUN cd ./packages/opal-common && python setup.py install
# Make sure scripts in .local are usable:
ENV PATH=/opal:/root/.local/bin:$PATH
# run gunicorn
CMD ["./start.sh"]


# STANDALONE IMAGE ----------------------------------
# ---------------------------------------------------
FROM common AS client-standalone
# uvicorn config ------------------------------------
# install the opal-client package
RUN cd ./packages/opal-client && python setup.py install

# WARNING: do not change the number of workers on the opal client!
# only one worker is currently supported for the client.

# number of uvicorn workers
ENV UVICORN_NUM_WORKERS=1
# uvicorn asgi app
ENV UVICORN_ASGI_APP=opal_client.main:app
# uvicorn port
ENV UVICORN_PORT=7000
# disable inline OPA
ENV OPAL_INLINE_OPA_ENABLED=false

# expose opal client port
EXPOSE 7000
USER opal

RUN mkdir -p /opal/backup
VOLUME /opal/backup


# IMAGE to extract OPA from official image ----------
# ---------------------------------------------------
FROM alpine:latest AS opa-extractor
USER root

RUN apk update && apk add skopeo tar
WORKDIR /opal

# copy opa from official docker image
ARG opa_image=openpolicyagent/opa
ARG opa_tag=1.9.0-static
RUN skopeo copy "docker://${opa_image}:${opa_tag}" docker-archive:./image.tar && \
  mkdir image && tar xf image.tar -C ./image && cat image/*.tar | tar xf - -C ./image -i && \
  find image/ -name "opa*" -type f -executable -print0 | xargs -0 -I "{}" cp {} ./opa && chmod 755 ./opa && \
  rm -r image image.tar


# OPA CLIENT IMAGE ----------------------------------
# Using standalone image as base --------------------
# ---------------------------------------------------
FROM client-standalone AS client

# Temporarily move back to root for additional setup
USER root

# copy opa from opa-extractor
COPY --from=opa-extractor /opal/opa ./opa

# enable inline OPA
ENV OPAL_INLINE_OPA_ENABLED=true
ENV OPAL_INLINE_OPA_EXEC_PATH=/opal/opa
# expose opa port
EXPOSE 8181
USER opal

# EOPA BINARY DOWNLOAD STAGE ------------------------
# ---------------------------------------------------
FROM alpine:latest AS eopa-extractor
USER root

# Install download dependencies
RUN apk add --no-cache wget

# Set working directory
WORKDIR /download

# Download pre-built EOPA binary based on architecture
ARG eopa_tag=v1.44.0
ARG TARGETARCH
RUN case "${TARGETARCH}" in \
        "amd64") EOPA_ARCH="x86_64" ;; \
        "arm64") EOPA_ARCH="arm64" ;; \
        *) echo "Unsupported architecture: ${TARGETARCH}" && exit 1 ;; \
    esac && \
    echo "Downloading EOPA for Linux_${EOPA_ARCH}" && \
    wget -O eopa "https://github.com/open-policy-agent/eopa/releases/download/${eopa_tag}/eopa_Linux_${EOPA_ARCH}" && \
    chmod +x eopa

# EOPA CLIENT IMAGE ---------------------------------
# Using standalone image as base --------------------
# ---------------------------------------------------
FROM client-standalone AS client-eopa

# Temporarily move back to root for additional setup
USER root

# copy eopa from eopa-extractor
COPY --from=eopa-extractor /download/eopa ./eopa

# enable inline EOPA
ENV OPAL_POLICY_STORE_TYPE=OPA
ENV OPAL_INLINE_OPA_ENABLED=true
ENV OPAL_INLINE_OPA_EXEC_PATH=/opal/eopa
# expose eopa port (same as OPA)
EXPOSE 8181
USER opal

# CEDAR CLIENT IMAGE --------------------------------
# Using standalone image as base --------------------
# ---------------------------------------------------
# Extract the Cedar Agent binary from the existing image
# CEDAR AGENT DOWNLOAD STAGE -----------------------
# Stage to locate and extract the cedar-agent binary
FROM permitio/cedar-agent:0.2.1 AS cedar-extractor

FROM client-standalone AS client-cedar

# Temporarily move back to root for additional setup
USER root

COPY --from=cedar-extractor /agent/cedar-agent /bin/cedar-agent
RUN chmod +x /bin/cedar-agent

# enable inline Cedar agent
ENV OPAL_POLICY_STORE_TYPE=CEDAR
ENV OPAL_INLINE_CEDAR_ENABLED=true
ENV OPAL_INLINE_CEDAR_EXEC_PATH=/bin/cedar-agent
ENV OPAL_INLINE_CEDAR_CONFIG='{"addr": "0.0.0.0:8180"}'
ENV OPAL_POLICY_STORE_URL=http://localhost:8180
# expose cedar port
EXPOSE 8180
USER opal

# SERVER IMAGE --------------------------------------
# ---------------------------------------------------
FROM common AS server

RUN apt-get update && apt-get install -y openssh-client git && apt-get clean
RUN git config --global core.symlinks false # Mitigate CVE-2024-32002

USER opal

# Potentially trust POLICY REPO HOST ssh signature --
# opal trackes a remote (git) repository and fetches policy (e.g rego) from it.
# however, if the policy repo uses an ssh url scheme, authentication to said repo
# is done via ssh, and without adding the repo remote host (i.e: github.com) to
# the ssh known hosts file, ssh will issue output an interactive prompt that
# looks something like this:
#   The authenticity of host 'github.com (192.30.252.131)' can't be established.
#   RSA key fingerprint is 16:27:ac:a5:76:28:1d:52:13:1a:21:2d:bz:1d:66:a8.
#   Are you sure you want to continue connecting (yes/no)?
# if the docker build arg `TRUST_POLICY_REPO_HOST_SSH_FINGERPRINT` is set to `true`
# (default), the host specified by `POLICY_REPO_HOST` build arg (i.e: `github.com`)
# will be added to the known ssh hosts file at build time and prevent said prompt
# from showing.
ARG TRUST_POLICY_REPO_HOST_SSH_FINGERPRINT="true"
ARG POLICY_REPO_HOST="github.com"

RUN if [ "$TRUST_POLICY_REPO_HOST_SSH_FINGERPRINT" = "true" ] ; then \
  mkdir -p ~/.ssh && \
  chmod 0700 ~/.ssh && \
  ssh-keyscan -t rsa ${POLICY_REPO_HOST} >> ~/.ssh/known_hosts ; fi

USER root

# install the opal-server package
RUN cd ./packages/opal-server && python setup.py install

# uvicorn config ------------------------------------

# number of uvicorn workers
ENV UVICORN_NUM_WORKERS=1
# uvicorn asgi app
ENV UVICORN_ASGI_APP=opal_server.main:app
# uvicorn port
ENV UVICORN_PORT=7002

# opal configuration --------------------------------
# if you are not setting OPAL_DATA_CONFIG_SOURCES for some reason,
# override this env var with the actual public address of the server
# container (i.e: if you are running in docker compose and the server
# host is `opalserver`, the value will be: http://opalserver:7002/policy-data)
# `host.docker.internal` value will work better than `localhost` if you are
# running dockerized opal server and client on the same machine
ENV OPAL_ALL_DATA_URL=http://host.docker.internal:7002/policy-data
# Use fixed path for the policy repo - so new leader would use the same directory without re-cloning it.
# That's ok when running in docker and fs is ephemeral (repo in a bad state would be fixed by restarting container).
ENV OPAL_POLICY_REPO_REUSE_CLONE_PATH=true

# expose opal server port
EXPOSE 7002
USER opal

# ===================== ALPINE VARIANTS =====================
# BUILD STAGE (ALPINE) --------------------------------------
# -----------------------------------------------------------
FROM python:3.10-alpine AS build-stage-alpine
ARG LIBGIT2_VERSION=1.7.2
WORKDIR /app/
RUN apk add --no-cache \
  bash \
  build-base \
  musl-dev \
  libffi-dev \
  openssl-dev \
  pkgconfig \
  cmake \
  libssh2-dev \
  http-parser-dev \
  linux-headers \
  git \
  openssh-client \
  jq \
  wget
RUN wget -O /tmp/libgit2.tar.gz https://github.com/libgit2/libgit2/archive/refs/tags/v${LIBGIT2_VERSION}.tar.gz && \
  tar -xzf /tmp/libgit2.tar.gz -C /tmp && \
  cd /tmp/libgit2-${LIBGIT2_VERSION} && \
  cmake -S . -B build \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX=/usr/local \
    -DBUILD_SHARED_LIBS=ON \
    -DBUILD_TESTS=OFF \
    -DUSE_SSH=ON && \
  cmake --build build --config Release --target install && \
  rm -rf /tmp/libgit2*
COPY ./packages/requires.txt ./base_requires.txt
COPY ./packages/opal-common/requires.txt ./common_requires.txt
COPY ./packages/opal-client/requires.txt ./client_requires.txt
COPY ./packages/opal-server/requires.txt ./server_requires.txt
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r ./base_requires.txt -r ./common_requires.txt -r ./client_requires.txt -r ./server_requires.txt

# COMMON IMAGE (ALPINE) -------------------------------------
# -----------------------------------------------------------
FROM python:3.10-alpine AS common-alpine
RUN rm -r /usr/local/lib/python3.10/site-packages || true
COPY --from=build-stage-alpine /usr/local /usr/local
RUN adduser -D -h /opal -s /bin/bash opal && apk add --no-cache bash netcat-openbsd jq wget
RUN apk add --no-cache libssh2 http-parser
WORKDIR /opal
COPY scripts/wait-for.sh .
RUN chmod +x ./wait-for.sh
RUN ln -s /opal/wait-for.sh /usr/wait-for.sh
COPY ./scripts/start.sh .
RUN chmod +x ./start.sh
RUN ln -s /opal/start.sh /start.sh
COPY ./scripts/gunicorn_conf.py .
COPY ./README.md .
COPY ./packages ./packages/
RUN cd ./packages/opal-common && python setup.py install
ENV PATH=/opal:/root/.local/bin:$PATH
CMD ["./start.sh"]


# STANDALONE IMAGE (ALPINE) ---------------------------------
# -----------------------------------------------------------
FROM common-alpine AS client-standalone-alpine
RUN cd ./packages/opal-client && python setup.py install
ENV UVICORN_NUM_WORKERS=1
ENV UVICORN_ASGI_APP=opal_client.main:app
ENV UVICORN_PORT=7000
ENV OPAL_INLINE_OPA_ENABLED=false
EXPOSE 7000
USER opal
RUN mkdir -p /opal/backup
VOLUME /opal/backup


# OPA CLIENT IMAGE (ALPINE) -------------------------
# Using standalone image as base --------------------
# ---------------------------------------------------
FROM client-standalone-alpine AS client-alpine
USER root
COPY --from=opa-extractor /opal/opa ./opa
ENV OPAL_INLINE_OPA_ENABLED=true
ENV OPAL_INLINE_OPA_EXEC_PATH=/opal/opa


# EOPA CLIENT IMAGE (ALPINE) ------------------------
# Using standalone image as base --------------------
# ---------------------------------------------------
FROM client-standalone-alpine AS client-eopa-alpine
USER root
COPY --from=eopa-extractor /download/eopa ./eopa
ENV OPAL_POLICY_STORE_TYPE=OPA
ENV OPAL_INLINE_OPA_ENABLED=true
ENV OPAL_INLINE_OPA_EXEC_PATH=/opal/eopa
EXPOSE 8181
USER opal


# CEDAR CLIENT IMAGE (ALPINE) -----------------------
# Using standalone image as base --------------------
# ---------------------------------------------------
FROM client-standalone-alpine AS client-cedar-alpine
USER root
COPY --from=cedar-extractor /agent/cedar-agent /bin/cedar-agent
RUN chmod +x /bin/cedar-agent
ENV OPAL_POLICY_STORE_TYPE=CEDAR
ENV OPAL_INLINE_CEDAR_ENABLED=true
ENV OPAL_INLINE_CEDAR_EXEC_PATH=/bin/cedar-agent
ENV OPAL_INLINE_CEDAR_CONFIG='{"addr": "0.0.0.0:8180"}'
ENV OPAL_POLICY_STORE_URL=http://localhost:8180
EXPOSE 8180
USER opal


# SERVER IMAGE (ALPINE) -----------------------------
# ---------------------------------------------------
FROM common-alpine AS server-alpine
RUN apk add --no-cache openssh-client git libssh2
RUN git config --global core.symlinks false
USER opal
ARG TRUST_POLICY_REPO_HOST_SSH_FINGERPRINT="true"
ARG POLICY_REPO_HOST="github.com"
RUN if [ "$TRUST_POLICY_REPO_HOST_SSH_FINGERPRINT" = "true" ] ; then \
  mkdir -p ~/.ssh && \
  chmod 0700 ~/.ssh && \
  ssh-keyscan -t rsa ${POLICY_REPO_HOST} >> ~/.ssh/known_hosts ; fi
USER root
RUN cd ./packages/opal-server && python setup.py install
ENV UVICORN_NUM_WORKERS=1
ENV UVICORN_ASGI_APP=opal_server.main:app
ENV UVICORN_PORT=7002
ENV OPAL_ALL_DATA_URL=http://host.docker.internal:7002/policy-data
ENV OPAL_POLICY_REPO_REUSE_CLONE_PATH=true
EXPOSE 7002
USER opal
