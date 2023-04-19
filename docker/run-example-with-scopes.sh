#!/bin/bash

set -e

if [ ! -f "docker-compose-scopes-example.yml" ]; then
   echo "did not find compose file - run this script from the 'docker/' directory under opal root!"
   exit
fi

echo "------------------------------------------------------------------"
echo "This script will run the docker-compose-scopes-example.yml example"
echo "configuration, and demonstrates how to correctly create scopes in OPAL server"
echo "------------------------------------------------------------------"

echo "Run OPAL server with scopes in the background"
docker compose -f docker-compose-scopes-example.yml up -d opal_server --remove-orphans

sleep 2

echo "Create scope 'myscope'"
curl --request PUT 'http://localhost:7002/scopes' --header 'Content-Type: application/json' --data-raw '{
  "scope_id": "myscope",
  "policy": {
    "source_type": "git",
    "url": "https://github.com/permitio/opal-example-policy-repo",
    "auth": {
      "auth_type": "none"
    },
    "extensions": [
      ".rego",
      ".json"
    ],
    "manifest": ".manifest",
    "poll_updates": "true",
    "branch": "master"
  },
  "data": {
    "entries": []
  }
}'

echo "Create scope 'herscope'"
curl --request PUT 'http://localhost:7002/scopes' --header 'Content-Type: application/json' --data-raw '{
  "scope_id": "herscope",
  "policy": {
    "source_type": "git",
    "url": "https://github.com/permitio/opal-example-policy-repo",
    "auth": {
      "auth_type": "none"
    },
    "extensions": [
      ".rego",
      ".json"
    ],
    "manifest": ".manifest",
    "poll_updates": true,
    "branch": "master"
  },
  "data": {
    "entries": []
  }
}'

echo "Bring up OPAL clients to use newly created scopes"
docker compose -f docker-compose-scopes-example.yml up
