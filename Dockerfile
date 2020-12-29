FROM openpolicyagent/opa as opa

# BUILD STAGE ---------------------------------------
# split this stage to save time and reduce image size
# ---------------------------------------------------
FROM python:3.8-alpine as BuildStage
# install linux libraries necessary to compile some python packages
RUN apk update
RUN apk add --update --no-cache --virtual .build-deps gcc git build-base alpine-sdk python3-dev musl-dev postgresql-dev libffi-dev libressl-dev
# from now on, work in the /app directory
WORKDIR /app/
# Layer dependency install (for caching)
COPY requirements.txt requirements.txt
# install python deps
RUN pip install --user -r requirements.txt

# this will be overriden in github action
# default value works for local runs (with private ssh key)
ARG READ_ONLY_GITHUB_TOKEN="<you must pass a token>"

# install websockets lib from github (this is our library and may update a lot)
RUN pip install --user git+https://${READ_ONLY_GITHUB_TOKEN}@github.com/acallasec/websockets.git

# clone OPA
WORKDIR /opaclone
RUN git clone https://github.com/open-policy-agent/opa.git

# MAIN IMAGE ----------------------------------------
# most of the time only this image should be built
# ---------------------------------------------------
FROM python:3.8-alpine
# bash is needed for ./start/sh script
# libc6-compat and libstdc are needed for opa binary
RUN apk add --update --no-cache bash libc6-compat libstdc++
# Fucking shit that libwasmer.so needs
RUN ln -s /lib/libc.musl-x86_64.so.1 /lib/ld-linux-x86-64.so.2
# copy opa from official image (main binary and lib for web assembly)
COPY --from=opa /opa /
COPY --from=BuildStage /opaclone/opa/vendor/github.com/wasmerio/go-ext-wasm/wasmer/libwasmer.so /usr/lib/opa/libwasmer.so
# copy libraries from build stage
COPY --from=BuildStage /root/.local /root/.local
# copy wait-for-it (use only for development! e.g: docker compose)
COPY scripts/wait-for-it.sh /usr/wait-for-it.sh
RUN chmod +x /usr/wait-for-it.sh
# copy startup script
COPY ./scripts/start.sh /start.sh
RUN chmod +x /start.sh
# copy app code
COPY . ./
# install sidecar package
RUN python setup.py develop
# Make sure scripts in .local are usable:
ENV PATH=/:/root/.local/bin:$PATH
# by default, the backend is at port 8000 on the docker host
# in prod, you must pass the correct url
ENV AUTHZ_SERVICE_URL=https://api.authorizon.com
ENV CLIENT_TOKEN="MUST BE DEFINED"
# expose sidecar port
EXPOSE 7000
# expose opa directly
EXPOSE 8181
# run gunicorn
CMD ["/start.sh"]