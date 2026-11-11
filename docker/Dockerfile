# syntax=docker/dockerfile:1.19@sha256:b6afd42430b15f2d2a4c5a02b919e98a525b785b1aaff16747d2f623364e39b6
# The syntax line must stay first. COPY --exclude below needs dockerfile frontend 1.19 or later
# (1.17 and 1.18 reject the flag). The digest pins the frontend that builds every image; when
# you change the tag, update the digest with it (docker buildx imagetools inspect <tag>).
# Every image builds on Wolfi, with Wolfi's own Python package: PYTHON_VERSION, the one Python
# the packages' python_requires admits, is declared once here for the whole file.
ARG PYTHON_VERSION=3.14

# WOLFI BASE ----------------------------------------
# The one base of every stage below. wolfi-base publishes :latest only and rebuilds it daily, so
# it is pinned by digest; Dependabot proposes digest bumps. Its /etc/apk/world pins each of its
# own packages (glibc, openssl, busybox, ...) to the version it ships, so apk upgrade cannot move
# them: a fix to one of them comes with a new digest.
# ---------------------------------------------------
FROM cgr.dev/chainguard/wolfi-base:latest@sha256:94fa13e26d449f7d78dbcd02d12ea37a0da80d24fcc3e1f17b95d515dec607a7 AS wolfi-base

# PYTHON BASE ---------------------------------------
# ---------------------------------------------------
FROM wolfi-base AS python-base
ARG PYTHON_VERSION
# The ca-certificates floor (20261020-r0) drops the root of the compromised eMudhra CAs; declared
# to apk, so a stale index fails here with apk's own version error.
RUN apk add --no-cache "python-${PYTHON_VERSION}" bash 'ca-certificates-bundle>=20261020-r0'

# BUILD STAGE ---------------------------------------
# split this stage to save time and reduce image size
# ---------------------------------------------------
FROM python-base AS build-stage
ARG PYTHON_VERSION
# from now on, work in the /app directory
WORKDIR /app/
# Layer dependency install (for caching)
COPY ./packages/requires.txt ./base_requires.txt
COPY ./packages/opal-common/requires.txt ./common_requires.txt
COPY ./packages/opal-client/requires.txt ./client_requires.txt
COPY ./packages/opal-server/requires.txt ./server_requires.txt
# OPAL and its dependencies go into a venv, apart from the packages apk owns.
# --system-site-packages keeps the user site on sys.path, so `pip install --user` in an image
# built FROM these (the documented way to add a fetch provider) keeps working.
RUN "python${PYTHON_VERSION}" -m venv --system-site-packages /opt/venv
ENV PATH=/opt/venv/bin:$PATH
# install python deps. setuptools is installed explicitly, at packages/requires.txt's floor or
# newer, since a new venv holds none. Capped at the major: the images still install OPAL with the
# deprecated `setup.py install`, so a new setuptools major could break an unchanged rebuild (82
# already dropped pkg_resources).
RUN pip install --no-cache-dir --upgrade pip 'setuptools>=84.1.0,<85' && pip install --no-cache-dir -r ./base_requires.txt -r ./common_requires.txt -r ./client_requires.txt -r ./server_requires.txt

# COMMON IMAGE --------------------------------------
# ---------------------------------------------------
FROM python-base AS common

# copy the venv from the build stage (without the tools only the build needed)
COPY --from=build-stage /opt/venv /opt/venv
# The venv's bin before /usr/bin, so `python` and `pip` are the venv's (docker exec too), and
# /opal/.local/bin for what `pip install --user` adds in an image built FROM these.
ENV PATH=/opal:/opal/.local/bin:/opt/venv/bin:$PATH

# Add the non-root user opal: uid and gid 1000, home /opal. Its /etc/passwd entry is what ssh
# needs to fetch a policy repo over SSH; under a uid with no entry, ssh refuses to run.
RUN addgroup -g 1000 opal && adduser -D -u 1000 -G opal -h /opal -s /bin/bash opal
WORKDIR /opal

# copy wait-for script (create link at old path to maintain backward compatibility)
COPY scripts/wait-for.sh .
RUN chmod +x ./wait-for.sh
RUN ln -s /opal/wait-for.sh /usr/wait-for.sh

# netcat (nc) is used by the wait-for.sh script.
# check_trust_store.py fails the build if the system bundle or certifi's still trusts the
# compromised eMudhra CAs; it runs after every step that installs OS packages, and stays in the
# image for re-checking it.
COPY scripts/check_trust_store.py .
RUN apk add --no-cache netcat-openbsd jq wget && \
  python check_trust_store.py

# copy startup script (create link at old path to maintain backward compatibility)
COPY ./scripts/start.sh .
RUN chmod +x ./start.sh
RUN ln -s /opal/start.sh /start.sh
# copy gunicorn_config
COPY ./scripts/gunicorn_conf.py .
# copy app code

COPY ./README.md .
# --exclude as well as .dockerignore: a build from a Git context (docker build <git-url>)
# skips .dockerignore. The trust-store test's fixture holds the compromised eMudhra
# certificates, and a search of the image's files for them would report it, even though
# nothing trusts it.
COPY --exclude=**/tests/*.pem ./packages ./packages/
# install the opal-common package
RUN cd ./packages/opal-common && python setup.py install
# With OPAL_ENABLE_DATADOG_APM, start.sh runs gunicorn under ddtrace-run. ddtrace 4 traces every
# websocket message by default (3.x did not), which would turn each pub/sub update into spans.
# Keep the 3.x behaviour; set it to true to opt in. configure_apm applies the same default.
ENV DD_TRACE_WEBSOCKET_MESSAGES_ENABLED=false
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
FROM wolfi-base AS opa-extractor
USER root

# busybox's tar and find lack the flags the copy below uses
RUN apk add --no-cache skopeo gnutar findutils
WORKDIR /opal

# copy opa from official docker image. `opa_image` / `opa_tag` are documented build
# args (#322) for supplying your own OPA image, so this stays a skopeo copy rather than
# a `FROM`. `--override-arch` picks the TARGET architecture explicitly, so the binary
# is right for arm64 even if this stage ever runs on the build host's platform.
#
# 1.21.4 (built with Go 1.27.3). Was 1.9.0, built with Go 1.25.1, which carries
# CVE-2025-68121 and later Go stdlib CVEs. OPA 1.19-1.21 tightened the compiler, so a
# policy that compiled on 1.9 can be rejected at load time: see
# documentation/docs/tutorials/opa-version-migration.mdx ("OPA bundled in the client image").
#
# The default is pinned by digest (the multi-arch index of `${opa_image}:${opa_tag}`).
# When you override opa_image or opa_tag, pass the new image's digest as opa_digest, or an
# empty opa_digest to take the tag as it resolves.
ARG opa_image=openpolicyagent/opa
ARG opa_tag=1.21.4-static
ARG opa_digest=sha256:47f93480b09e24c220ae75f1e9133585ba6d698059951668d35e6a4fc32ebc82
ARG TARGETARCH
RUN src="docker://${opa_image}:${opa_tag}" && \
  if [ -n "${opa_digest}" ]; then \
    skopeo inspect --raw "${src}" > manifest.json && \
    got="sha256:$(sha256sum manifest.json | cut -d' ' -f1)" && \
    { [ "${got}" = "${opa_digest}" ] || { echo "${opa_image}:${opa_tag} is ${got}, expected ${opa_digest}; pass --build-arg opa_digest=<digest> (or an empty one) when overriding opa_image or opa_tag" >&2; exit 1; }; } && \
    src="docker://${opa_image}@${opa_digest}"; \
  fi && \
  skopeo copy --override-arch "${TARGETARCH}" "${src}" docker-archive:./image.tar && \
  mkdir image && tar xf image.tar -C ./image && cat image/*.tar | tar xf - -C ./image -i && \
  find image/ -name "opa*" -type f -executable -print0 | xargs -0 -I "{}" cp {} ./opa && chmod 755 ./opa && \
  rm -rf image image.tar manifest.json


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
FROM wolfi-base AS eopa-extractor
USER root

# Install download dependencies
RUN apk add --no-cache wget

# Set working directory
WORKDIR /download

# Download the pre-built EOPA binary for the target architecture, checked against
# the release's own checksums.txt. Bump the tag and both sums together.
#
# v1.45.1 is the LAST EOPA release: open-policy-agent/eopa is archived upstream,
# so nothing newer will ship. That binary is built with go1.25.4 on OPA v1.10.1 and
# bundles jackc/pgx/v5 v5.7.6, so in the EOPA client image these stay unfixed for
# good: every pgx advisory fixed after 5.7.6 (5.9.x and later), every Go stdlib CVE
# fixed after 1.25.4, and every OPA server fix after 1.10.1 (e.g. 1.11.1's gzip-header
# memory exhaustion, 1.19.0's Compile API fix). Plan to retire the EOPA variant rather
# than wait for an upstream fix; the user docs say so where they offer opal-client-eopa.
ARG eopa_tag=v1.45.1
ARG EOPA_SHA256_x86_64=588ba9c7149b74ba0c497293615abca2aef668c29dbdef7cfe8a449829bf83fe
ARG EOPA_SHA256_arm64=1e8ed5b4f97d133f932a0af98656136f2ecda9bfdc68c82b3c63a999a43345d4
ARG TARGETARCH
RUN case "${TARGETARCH}" in \
        "amd64") EOPA_ARCH="x86_64"; EOPA_SHA256="${EOPA_SHA256_x86_64}" ;; \
        "arm64") EOPA_ARCH="arm64"; EOPA_SHA256="${EOPA_SHA256_arm64}" ;; \
        *) echo "Unsupported architecture: ${TARGETARCH}" && exit 1 ;; \
    esac && \
    echo "Downloading EOPA ${eopa_tag} for Linux_${EOPA_ARCH}" && \
    wget -O eopa "https://github.com/open-policy-agent/eopa/releases/download/${eopa_tag}/eopa_Linux_${EOPA_ARCH}" && \
    echo "${EOPA_SHA256}  eopa" | sha256sum -c - && \
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

# git and ssh run the git command-line fetch backend; ssh-keyscan fills known_hosts below.
RUN apk add --no-cache git openssh-client openssh-keyscan && \
  python check_trust_store.py

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
  ssh-keyscan -t ed25519,ecdsa,rsa ${POLICY_REPO_HOST} >> ~/.ssh/known_hosts ; fi

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

# SERVER TEST IMAGE ---------------------------------
# For CI only, never published: the server image plus what the git command-line tests need to
# run in it, under its busybox sh, git and ssh. git-daemon serves git:// and brings git-shell,
# which the tests' sshd runs; openssl makes their TLS certificates. The tests and their
# conftest.py come from a checkout mounted at run time.
# ---------------------------------------------------
FROM server AS server-test
USER root
COPY docker/server-test-requirements.txt /tmp/server-test-requirements.txt
RUN apk add --no-cache git-daemon openssh-server openssh-keygen openssl && \
  python check_trust_store.py && \
  pip install --no-cache-dir --require-hashes -r /tmp/server-test-requirements.txt
USER opal

# DEFAULT IMAGE -------------------------------------
# A build with no --target builds the last stage: the server image, not server-test.
# ---------------------------------------------------
FROM server
