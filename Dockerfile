FROM openpolicyagent/opa as opa

# BUILD STAGE ---------------------------------------
# split this stage to save time and reduce image size
# ---------------------------------------------------
FROM python:3.8-alpine as BuildStage
# install linux libraries necessary to compile some python packages
RUN apk update
RUN apk add --update --no-cache --virtual .build-deps gcc alpine-sdk python3-dev musl-dev postgresql-dev libffi-dev libressl-dev
# from now on, work in the /app directory
WORKDIR /app/
# Layer dependency install (for caching)
COPY requirements.txt requirements.txt
# install python deps
RUN pip install --user -r requirements.txt

# MAIN IMAGE ----------------------------------------
# most of the time only this image should be built
# ---------------------------------------------------
FROM python:3.8-alpine
# git is needed to fetch websockets lib
RUN apk add --update --no-cache git
# copy opa from official image
COPY --from=opa /opa /
# copy libraries from build stage
COPY --from=BuildStage /root/.local /root/.local
# install websockets lib from github (this is our library and may update a lot)
RUN pip install --user git+https://61c18c826840c46f67f7fdada5f0928104dbe91a@github.com/acallasec/websockets.git
# copy app code
COPY . ./
# install sidecar package
RUN python setup.py develop
# Make sure scripts in .local are usable:
ENV PATH=/:/root/.local/bin:$PATH
# by default, the backend is at port 8000 on the docker host
# in prod, you must pass the correct url
ENV AUTHZ_SERVICE_URL="http://host.docker.internal:8000"
# expose sidecar port
EXPOSE 7000
# run gunicorn
CMD gunicorn -b 0.0.0.0:7000 -k uvicorn.workers.UvicornWorker --workers=1 horizon.main:app