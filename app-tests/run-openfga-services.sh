#!/bin/bash

# Start the services in detached mode
echo "Starting OpenFGA and OPAL services..."
docker compose -f docker-compose-app-tests-openfga.yml up -d

# Wait for services to initialize (adjust time if needed)
echo "Waiting for services to initialize..."
sleep 15

echo "Services started in detached mode"