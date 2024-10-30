#!/bin/bash
# Start OpenFGA in the background
/usr/local/bin/openfga run --playground-enabled=false &
OPENFGA_PID=$!

# Start OPAL client
./start.sh &
OPAL_PID=$!

# Handle signals
trap "kill $OPENFGA_PID $OPAL_PID" SIGTERM SIGINT

# Wait for both processes
wait $OPENFGA_PID $OPAL_PID