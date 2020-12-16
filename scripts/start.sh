#! /usr/bin/env sh
set -e

# Start Gunicorn
exec gunicorn -b 0.0.0.0:7000 -k uvicorn.workers.UvicornWorker --workers=1 horizon.main:app