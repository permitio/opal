# BUILD STAGE ---------------------------------------
# split this stage to save time and reduce image size
# ---------------------------------------------------
# NOTE: at the moment we use alpine3.11 instead of alpine latest
# due to https://github.com/gliderlabs/docker-alpine/issues/539
# which broke alpine dns lookup methods starting at alpine 3.12.
FROM python:3.8-alpine3.11 as BuildStage
# update apk cache
RUN apk update
# TODO: remove this when upgrading to a new alpine version
# more details: https://github.com/pyca/cryptography/issues/5771
ENV CRYPTOGRAPHY_DONT_BUILD_RUST=1
# install linux libraries necessary to compile some python packages
RUN apk add --update --no-cache --virtual .build-deps gcc git build-base alpine-sdk python3-dev musl-dev postgresql-dev libffi-dev libressl-dev
# from now on, work in the /app directory
WORKDIR /app/
# Layer dependency install (for caching)
COPY requirements.txt requirements.txt
# install python deps
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir --user -r requirements.txt


# COMMON IMAGE --------------------------------------
# ---------------------------------------------------
# NOTE: at the moment we use alpine3.11 instead of alpine latest
# due to https://github.com/gliderlabs/docker-alpine/issues/539
# which broke alpine dns lookup methods starting at alpine 3.12.
FROM python:3.8-alpine3.11 as common
# copy libraries from build stage
COPY --from=BuildStage /root/.local /root/.local
# needed for rookout
RUN apk add g++ python3-dev linux-headers
# copy wait-for script
COPY scripts/wait-for.sh /usr/wait-for.sh
RUN chmod +x /usr/wait-for.sh
# copy startup script
COPY ./scripts/start.sh /start.sh
RUN chmod +x /start.sh
# copy gunicorn_config
COPY ./scripts/gunicorn_conf.py /gunicorn_conf.py
# copy app code
COPY . ./
# install sidecar package
RUN python setup/setup_common.py install
# Make sure scripts in .local are usable:
ENV PATH=/:/root/.local/bin:$PATH
# run gunicorn
CMD ["/start.sh"]


# STANDALONE IMAGE ----------------------------------
# ---------------------------------------------------
FROM common as client-standalone
# install sidecar client package
RUN python setup/setup_client.py install
# uvicorn config ------------------------------------

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


# CLIENT IMAGE --------------------------------------
# Using standalone image as base --------------------
# ---------------------------------------------------
FROM client-standalone as client
# curl is needed for next section
RUN apk add --update --no-cache curl
# copy opa from official image (main binary and lib for web assembly)
RUN curl -L -o /opa https://openpolicyagent.org/downloads/latest/opa_linux_amd64_static && chmod 755 /opa
# enable inline OPA
ENV OPAL_INLINE_OPA_ENABLED=true
# expose opa port
EXPOSE 8181


# SERVER IMAGE --------------------------------------
# ---------------------------------------------------
FROM common as server
# git is needed by opal server (for policy repo tracking)
RUN apk add --update --no-cache git openssh

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

RUN if [[ "$TRUST_POLICY_REPO_HOST_SSH_FINGERPRINT" == "true" ]] ; then \
    mkdir -p /root/.ssh && \
    chmod 0700 /root/.ssh && \
    ssh-keyscan -t rsa ${POLICY_REPO_HOST} >> /root/.ssh/known_hosts ; fi

# install sidecar server package
RUN python setup/setup_server.py install

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

# expose opal server port
EXPOSE 7002
