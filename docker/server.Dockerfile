# BUILD STAGE ---------------------------------------
# split this stage to save time and reduce image size
# ---------------------------------------------------
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
RUN pip install --upgrade pip && pip install --user -r requirements.txt

# MAIN IMAGE ----------------------------------------
# most of the time only this image should be built
# ---------------------------------------------------
FROM python:3.8-alpine3.11
# bash is needed for ./start/sh script
# git is needed by opal server (for policy repo tracking)
RUN apk add --update --no-cache bash git openssh
# copy libraries from build stage
COPY --from=BuildStage /root/.local /root/.local
# copy wait-for-it (use only for development! e.g: docker compose)
COPY scripts/wait-for-it.sh /usr/wait-for-it.sh
RUN chmod +x /usr/wait-for-it.sh
# copy startup script
COPY ./scripts/start.sh /start.sh
RUN chmod +x /start.sh

# add POLICY REPO HOST to trusted identities (can be cancelled during docker build)
ARG TRUST_POLICY_REPO_HOST_SSH_FINGERPRINT="true"
ARG POLICY_REPO_HOST="github.com"

RUN if [[ "$TRUST_POLICY_REPO_HOST_SSH_FINGERPRINT" == "true" ]] ; then \
    mkdir -p /root/.ssh && \
    chmod 0700 /root/.ssh && \
    ssh-keyscan -t rsa ${POLICY_REPO_HOST} >> /root/.ssh/known_hosts ; fi

# copy app code
COPY . ./
# install sidecar package
RUN python setup/setup_server.py install

# Make sure scripts in .local are usable:
ENV PATH=/:/root/.local/bin:$PATH

# uvicorn config ------------------------------------

# number of uvicorn workers
ENV UVICORN_NUM_WORKERS=1
# uvicorn asgi app
ENV UVICORN_ASGI_APP=opal_server.main:app
# uvicorn port
ENV UVICORN_PORT=7002

# opal configuration --------------------------------
# ENV ...

# expose opal server port
EXPOSE 7002
# run gunicorn
CMD ["/start.sh"]