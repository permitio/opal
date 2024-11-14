#! /usr/bin/env bash
set -e

export GUNICORN_CONF=${GUNICORN_CONF:-./gunicorn_conf.py}
export GUNICORN_TIMEOUT=${GUNICORN_TIMEOUT:-30}
export GUNICORN_KEEP_ALIVE_TIMEOUT=${GUNICORN_KEEP_ALIVE_TIMEOUT:-5}

if [[ -z "${OPAL_BROADCAST_URI}" && "${UVICORN_NUM_WORKERS}" != "1" ]]; then
  echo "OPAL_BROADCAST_URI must be set when having multiple workers"
  exit 1
fi

prefix=""
# Start Gunicorn
if [[ -z "${OPAL_ENABLE_DATADOG_APM}" && "${OPAL_ENABLE_DATADOG_APM}" = "true" ]]; then
	prefix=ddtrace-run
fi
(set -x; exec $prefix gunicorn -b 0.0.0.0:${UVICORN_PORT} -k uvicorn.workers.UvicornWorker --workers=${UVICORN_NUM_WORKERS} -c ${GUNICORN_CONF} ${UVICORN_ASGI_APP} -t ${GUNICORN_TIMEOUT} --keep-alive ${GUNICORN_KEEP_ALIVE_TIMEOUT})
