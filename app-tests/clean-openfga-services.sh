#!/bin/bash

# Stop and remove containers, networks, volumes
echo "Cleaning up services..."
docker compose -f docker-compose-app-tests-openfga.yml down -v

echo "Cleanup complete"