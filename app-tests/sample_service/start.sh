#!/bin/sh

# Activate virtual environment
. /venv/bin/activate

# Start OpenResty
openresty -g "daemon off;" &

# Start Flask app
flask run --host=0.0.0.0 --port=5000