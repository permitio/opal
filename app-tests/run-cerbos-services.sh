#!/bin/bash
set -e

# Make paths below independent of the caller's cwd.
cd "$(dirname "$0")"

echo "Building client-cerbos image..."
docker compose -f docker-compose-app-tests-cerbos.yml build

echo "Starting Cerbos and OPAL services..."
docker compose -f docker-compose-app-tests-cerbos.yml up -d

echo "Waiting for opal-client to finish syncing policy..."
for _ in $(seq 1 60); do
  if curl -sf http://localhost:7766/ready > /dev/null 2>&1; then
    echo "Services ready"
    exit 0
  fi
  sleep 2
done

echo "opal-client did not become ready in time" >&2
docker compose -f docker-compose-app-tests-cerbos.yml logs
exit 1
