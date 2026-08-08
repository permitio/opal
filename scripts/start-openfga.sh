#!/bin/bash
# Entrypoint for the client-openfga image.
#
# Starts the local OpenFGA server, waits for it to be healthy, and - unless
# OPAL_OPENFGA_STORE_ID was already provided - creates a fresh store and
# exports its id before handing off to the normal opal-client startup script.
#
# This process (not OPAL's own inline-OpenFGA runner) owns the OpenFGA
# process, since the store id has to be known *before* opal-client starts -
# so OPAL_INLINE_OPENFGA_ENABLED is forced off below.
set -euo pipefail

OPENFGA_BIN="${OPAL_INLINE_OPENFGA_EXEC_PATH:-/usr/local/bin/openfga}"
OPENFGA_ADDR="0.0.0.0:8080"
OPENFGA_HEALTH_URL="http://localhost:8080/healthz"

"$OPENFGA_BIN" run --http-addr="$OPENFGA_ADDR" --playground-enabled=false &

echo "Waiting for OpenFGA to become healthy..."
for _ in $(seq 1 60); do
  if curl -sf "$OPENFGA_HEALTH_URL" > /dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

if ! curl -sf "$OPENFGA_HEALTH_URL" > /dev/null 2>&1; then
  echo "OpenFGA did not become healthy in time" >&2
  exit 1
fi

if [ -z "${OPAL_OPENFGA_STORE_ID:-}" ]; then
  STORE_NAME="${OPENFGA_STORE_NAME:-opal-demo}"
  echo "OPAL_OPENFGA_STORE_ID not set, creating store '$STORE_NAME'..."
  STORE_ID=$(curl -sf -X POST "http://localhost:8080/stores" \
    -H "Content-Type: application/json" \
    -d "{\"name\": \"$STORE_NAME\"}" | jq -r '.id')

  if [ -z "$STORE_ID" ] || [ "$STORE_ID" = "null" ]; then
    echo "Failed to create OpenFGA store" >&2
    exit 1
  fi

  echo "Created OpenFGA store: $STORE_ID"
  export OPAL_OPENFGA_STORE_ID="$STORE_ID"
fi

export OPAL_INLINE_OPENFGA_ENABLED=false

exec ./start.sh
