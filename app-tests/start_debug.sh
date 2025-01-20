#!/bin/bash

echo "Starting Opal Server or Client with Debugpy in Debug Mode..."

# Set default values for variables if not already set
export GUNICORN_CONF=${GUNICORN_CONF:-./gunicorn_conf.py}
export UVICORN_PORT=${UVICORN_PORT:-8000}
export UVICORN_NUM_WORKERS=${UVICORN_NUM_WORKERS:-1}
export GUNICORN_TIMEOUT=${GUNICORN_TIMEOUT:-30}
export GUNICORN_KEEP_ALIVE_TIMEOUT=${GUNICORN_KEEP_ALIVE_TIMEOUT:-5}
#export UVICORN_ASGI_APP=${UVICORN_ASGI_APP:-opal_server.main:app}

# Check for OPAL_BROADCAST_URI when multiple workers are enabled
if [[ -z "${OPAL_BROADCAST_URI}" && "${UVICORN_NUM_WORKERS}" != "1" ]]; then
  echo "OPAL_BROADCAST_URI must be set when having multiple workers"
  exit 1
fi

# Ensure PYTHONPATH includes the directory for `opal_server`
export PYTHONPATH=/opal/packages/opal-server:$PYTHONPATH
export PYTHONPATH=/opal/packages/opal-client:$PYTHONPATH
echo "PYTHONPATH: $PYTHONPATH"

# Start Gunicorn with Debugpy
#exec python -m debugpy --listen 0.0.0.0:5678 --wait-for-client \
exec python -m debugpy --listen 0.0.0.0:5678 \
    -m gunicorn -b 0.0.0.0:${UVICORN_PORT} -k uvicorn.workers.UvicornWorker \
    --workers=${UVICORN_NUM_WORKERS} -c ${GUNICORN_CONF} ${UVICORN_ASGI_APP} \
    -t ${GUNICORN_TIMEOUT} --keep-alive ${GUNICORN_KEEP_ALIVE_TIMEOUT}
