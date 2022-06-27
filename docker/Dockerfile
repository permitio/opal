# BUILD STAGE ---------------------------------------
# split this stage to save time and reduce image size
# ---------------------------------------------------
FROM python:3.10 as BuildStage
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
FROM python:3.10-slim as common

# copy libraries from build stage (This won't copy redundant libraries we used in BuildStage)
COPY --from=BuildStage /usr/local /usr/local

# Add non-root user (with home dir at /opal)
RUN useradd -m -b / -s /bin/bash opal
WORKDIR /opal

# copy wait-for script (create link at old path to maintain backward compatibility)
COPY scripts/wait-for.sh .
RUN chmod +x ./wait-for.sh
RUN ln -s /opal/wait-for.sh /usr/wait-for.sh
# copy startup script (create link at old path to maintain backward compatibility)
COPY ./scripts/start.sh .
RUN chmod +x ./start.sh
RUN ln -s /opal/start.sh /start.sh
# copy gunicorn_config
COPY ./scripts/gunicorn_conf.py .
# copy app code
COPY . ./
# install the opal-common package
RUN cd ./packages/opal-common && python setup.py install
# Make sure scripts in .local are usable:
ENV PATH=/opal:/root/.local/bin:$PATH
# run gunicorn
CMD ["./start.sh"]


# STANDALONE IMAGE ----------------------------------
# ---------------------------------------------------
FROM common as client-standalone
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

# CLIENT IMAGE --------------------------------------
# Using standalone image as base --------------------
# ---------------------------------------------------
FROM client-standalone as client

# Temporarily move back to root for additional setup
USER root

RUN apt-get update && apt-get install -y curl netcat && apt-get clean

# copy opa from official image (main binary and lib for web assembly)
RUN curl -L -o ./opa https://openpolicyagent.org/downloads/latest/opa_linux_amd64_static && chmod 755 ./opa
# enable inline OPA
ENV OPAL_INLINE_OPA_ENABLED=true
# expose opa port
EXPOSE 8181
USER opal


# SERVER IMAGE --------------------------------------
# ---------------------------------------------------
FROM common as server

RUN apt-get update && apt-get install -y openssh-client git && apt-get clean

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
