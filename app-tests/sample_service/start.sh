#!/bin/sh

# Activate virtual environment
. /venv/bin/activate

# Start OpenResty
openresty -g "daemon off;" &

# Start Flask app
python -Xfrozen_modules=off -m flask run --host=0.0.0.0 --port=5000
