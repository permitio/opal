#! /usr/bin/env sh
set -e

# Start Gunicorn
exec gunicorn -b 0.0.0.0:${UVICORN_PORT} -k uvicorn.workers.UvicornWorker --workers=${UVICORN_NUM_WORKERS} ${UVICORN_ASGI_APP}