#!/bin/bash

# Make paths below independent of the caller's cwd.
cd "$(dirname "$0")"

echo "Cleaning up services..."
docker compose -f docker-compose-app-tests-cerbos.yml down -v

echo "Cleanup complete"
