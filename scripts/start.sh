#! /usr/bin/env sh
set -e

export GUNICORN_CONF=${GUNICORN_CONF:-/gunicorn_conf.py}

# Start Gunicorn
if [[ -z "${ENABLE_MONITORING}" && "${ENABLE_MONITORING}" = "true" ]]; then
  exec ddtrace-run gunicorn -b 0.0.0.0:${UVICORN_PORT} -k uvicorn.workers.UvicornWorker --workers=${UVICORN_NUM_WORKERS} -c ${GUNICORN_CONF} ${UVICORN_ASGI_APP}
else
  exec gunicorn -b 0.0.0.0:${UVICORN_PORT} -k uvicorn.workers.UvicornWorker --workers=${UVICORN_NUM_WORKERS} -c ${GUNICORN_CONF} ${UVICORN_ASGI_APP}
fi
