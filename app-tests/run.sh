#!/bin/bash
set -e

export OPAL_AUTH_PUBLIC_KEY
export OPAL_AUTH_PRIVATE_KEY
export OPAL_AUTH_PRIVATE_KEY_PASSPHRASE
export OPAL_AUTH_MASTER_TOKEN
export OPAL_CLIENT_TOKEN
export OPAL_DATA_SOURCE_TOKEN

# Store the initial directory and script directory
INITIAL_DIR=$(pwd)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

function generate_opal_keys {
  echo "- Generating OPAL keys"

  OPAL_AUTH_PRIVATE_KEY_PASSPHRASE="123456"
  ssh-keygen -q -t rsa -b 4096 -m pem -f opal_crypto_key -N "$OPAL_AUTH_PRIVATE_KEY_PASSPHRASE"
  OPAL_AUTH_PUBLIC_KEY="$(cat opal_crypto_key.pub)"
  OPAL_AUTH_PRIVATE_KEY="$(tr '\n' '_' < opal_crypto_key)"
  rm opal_crypto_key.pub opal_crypto_key

  # Generate tokens without requiring local OPAL installation
  echo "    Starting OPAL server for keygen"
  OPAL_AUTH_MASTER_TOKEN="$(openssl rand -hex 16)"
  docker rm -f --wait opal-server-keygen >/dev/null 2>&1 || true
  docker run --rm -d \
    --name opal-server-keygen \
    -e OPAL_AUTH_PUBLIC_KEY="$OPAL_AUTH_PUBLIC_KEY" \
    -e OPAL_AUTH_PRIVATE_KEY="$OPAL_AUTH_PRIVATE_KEY" \
    -e OPAL_AUTH_PRIVATE_KEY_PASSPHRASE="$OPAL_AUTH_PRIVATE_KEY_PASSPHRASE" \
    -e OPAL_AUTH_MASTER_TOKEN="$OPAL_AUTH_MASTER_TOKEN" \
    -e OPAL_AUTH_JWT_AUDIENCE=https://api.opal.ac/v1/ \
    -e OPAL_AUTH_JWT_ISSUER=https://opal.ac/ \
    -e OPAL_REPO_WATCHER_ENABLED=0 \
    -p 7002:7002 \
    permitio/opal-server:${OPAL_IMAGE_TAG:-latest}
  sleep 2;

  echo "    Obtaining tokens"
  set -o pipefail

  # Wait for the OPAL server to be ready
  echo "    Waiting for OPAL server to be ready..."
  timeout=30
  counter=0
  while ! curl -sf http://localhost:7002/ > /dev/null 2>&1; do
    counter=$((counter + 1))
    if [ $counter -gt $timeout ]; then
      echo "Timeout waiting for OPAL server to start"
      exit 1
    fi
    sleep 1
  done

  OPAL_CLIENT_TOKEN_RESPONSE="$(curl -s --request POST 'http://localhost:7002/token' \
    --header "Authorization: Bearer $OPAL_AUTH_MASTER_TOKEN" \
    --header 'Content-Type: application/json' \
    --data-raw '{"type": "client"}' 2>&1)"

  if [ $? -ne 0 ]; then
    echo "Failed to obtain OPAL_CLIENT_TOKEN:"
    echo "$OPAL_CLIENT_TOKEN_RESPONSE"
    exit 1
  fi

  # Extract token from JSON response
  OPAL_CLIENT_TOKEN="$(echo "$OPAL_CLIENT_TOKEN_RESPONSE" | grep -o '"token":"[^"]*"' | cut -d'"' -f4)"
  if [ -z "$OPAL_CLIENT_TOKEN" ]; then
    echo "Failed to extract client token from response:"
    echo "$OPAL_CLIENT_TOKEN_RESPONSE"
    exit 1
  fi

  # Obtain datasource token using curl
  echo "    Obtaining datasource token..."
  OPAL_DATA_SOURCE_TOKEN_RESPONSE="$(curl -s --request POST 'http://localhost:7002/token' \
    --header "Authorization: Bearer $OPAL_AUTH_MASTER_TOKEN" \
    --header 'Content-Type: application/json' \
    --data-raw '{"type": "datasource"}' 2>&1)"

  if [ $? -ne 0 ]; then
    echo "Failed to obtain OPAL_DATA_SOURCE_TOKEN:"
    echo "$OPAL_DATA_SOURCE_TOKEN_RESPONSE"
    exit 1
  fi

  # Extract token from JSON response
  OPAL_DATA_SOURCE_TOKEN="$(echo "$OPAL_DATA_SOURCE_TOKEN_RESPONSE" | grep -o '"token":"[^"]*"' | cut -d'"' -f4)"
  if [ -z "$OPAL_DATA_SOURCE_TOKEN" ]; then
    echo "Failed to extract datasource token from response:"
    echo "$OPAL_DATA_SOURCE_TOKEN_RESPONSE"
    exit 1
  fi

  set +o pipefail

  echo "    Stopping OPAL server for keygen"
  docker stop opal-server-keygen >/dev/null 2>&1 || true
  docker rm opal-server-keygen >/dev/null 2>&1 || true
  sleep 5;

  echo "- Create .env file"
  rm -f .env
  (
    echo "OPAL_AUTH_PUBLIC_KEY=\"$OPAL_AUTH_PUBLIC_KEY\"";
    echo "OPAL_AUTH_PRIVATE_KEY=\"$OPAL_AUTH_PRIVATE_KEY\"";
    echo "OPAL_AUTH_MASTER_TOKEN=\"$OPAL_AUTH_MASTER_TOKEN\"";
    echo "OPAL_CLIENT_TOKEN=\"$OPAL_CLIENT_TOKEN\"";
    echo "OPAL_AUTH_PRIVATE_KEY_PASSPHRASE=\"$OPAL_AUTH_PRIVATE_KEY_PASSPHRASE\""
  ) > .env
}

function prepare_policy_repo {
  echo "- Preparing policy repository"

  # Wait for Gitea to be ready and initialized
  echo "  Waiting for Gitea to be ready..."
  timeout=120
  counter=0
  while ! curl -sf http://localhost:3000 > /dev/null 2>&1; do
    counter=$((counter + 1))
    if [ $counter -gt $timeout ]; then
      echo "Timeout waiting for Gitea to start"
      exit 1
    fi
    sleep 1
  done

  # Wait for Gitea to be fully initialized (check if admin API is available)
  echo "  Waiting for Gitea to be fully initialized..."
  counter=0
  while ! curl -sf http://localhost:3000/api/v1/version > /dev/null 2>&1; do
    counter=$((counter + 1))
    if [ $counter -gt $timeout ]; then
      echo "Timeout waiting for Gitea to be initialized"
      exit 1
    fi
    sleep 2
  done
  echo "  Gitea is ready!"

  # Create initial admin user via CLI
  echo "  Creating initial admin user..."
  docker exec gitea gitea admin user create \
    --username gitea_admin \
    --password admin123 \
    --email admin@gitea.local \
    --admin \
    --must-change-password=false || echo "  Failed to create admin user, might already exist"

  # Prepare the local repository
  echo "  Creating temp repo for policy repository at $PWD/temp-repo..."
  rm -rf ./temp-repo
  mkdir -p temp-repo
  cd temp-repo
  git init

  # Configure git
  git config user.email "test@opal.local"
  git config user.name "OPAL Test"

  # Copy the policy files from opal-tests-policy-repo-main
  echo "  Copying policy files..."
  cp -r ../opal-tests-policy-repo-main/* .
  if [ -f ../opal-tests-policy-repo-main/.manifest ]; then
    cp ../opal-tests-policy-repo-main/.manifest .
  fi

  # Create initial commit
  git add .
  git commit -m "Initial policies from opal-tests-policy-repo"

  # Set up the repository URLs with embedded credentials
  export OPAL_POLICY_REPO_URL="http://gitea_admin:admin123@localhost:3000/gitea_admin/policy-repo.git"
  export OPAL_POLICY_REPO_URL_FOR_WEBHOOK="http://gitea:3000/gitea_admin/policy-repo.git"
  git remote add origin "$OPAL_POLICY_REPO_URL"

  # Check if repository already exists and delete if needed
  echo "  Checking if repository exists..."
  if curl -sf http://localhost:3000/api/v1/repos/gitea_admin/policy-repo > /dev/null 2>&1; then
    echo "  Repository already exists, deleting it..."
    curl -X DELETE http://localhost:3000/api/v1/repos/gitea_admin/policy-repo \
      -u "gitea_admin:admin123" 2>/dev/null || true
    sleep 2
  fi

  # Create repository via API
  echo "  Creating repository via API..."
  curl -X POST http://localhost:3000/api/v1/user/repos \
    -u "gitea_admin:admin123" \
    -H "Content-Type: application/json" \
    -d '{"name":"policy-repo","private":false,"auto_init":false}' 2>/dev/null || {
    echo "  Failed to create repository via API, trying push method..."
    # Fallback: try to create by pushing
    git push -u origin master:main 2>/dev/null || git push -u origin master 2>/dev/null || {
      echo "  Both methods failed to create repository"
      exit 1
    }
  }

  # Push to the repository
  echo "  Pushing to repository..."
  git push -u origin master:main || git push -u origin master

  # Create and push test branch
  export POLICY_REPO_BRANCH="test-$RANDOM$RANDOM"
  git checkout -b $POLICY_REPO_BRANCH
  git push -u origin $POLICY_REPO_BRANCH

  cd ..

  # Clone fresh for testing
  rm -rf ./opal-tests-policy-repo
  git clone "$OPAL_POLICY_REPO_URL" opal-tests-policy-repo
  cd opal-tests-policy-repo
  git checkout $POLICY_REPO_BRANCH
  cd ..
}

function compose {
  docker compose -f ./docker-compose-app-tests.yml --env-file .env "$@"
}

function check_clients_logged {
  echo "- Looking for msg '$1' in client's logs"
  compose logs --index 1 opal_client | grep -q "$1"
  compose logs --index 2 opal_client | grep -q "$1"
}

function check_no_error {
  # Without index would output all replicas
  if compose logs opal_client | grep -q 'ERROR'; then
    echo "- Found error in logs:"
    compose logs opal_client | grep 'ERROR'
    exit 1
  fi
}

function clean_up {
    ARG=$?
    # Ensure we're in the script directory for cleanup
    cd "$SCRIPT_DIR" 2>/dev/null || cd "$INITIAL_DIR"

    if [[ "$ARG" -ne 0 ]]; then
      echo "*** Test Failed ***"
      echo ""
      compose logs 2>/dev/null || echo "Could not retrieve logs"
    else
      echo "*** Test Passed ***"
      echo ""
    fi
    compose down 2>/dev/null || docker compose -f ./docker-compose-app-tests.yml down
    rm -rf ./opal-tests-policy-repo ./temp-repo ./gitea-data ./git-repos
    exit $ARG
}

function test_push_policy {
  echo "- Testing pushing policy $1"
  regofile="$1.rego"
  cd opal-tests-policy-repo
  echo "package $1" > "$regofile"
  git add "$regofile"
  git commit -m "Add $regofile"

  # Push to Gitea
  git push origin $POLICY_REPO_BRANCH
  cd -

  # Trigger webhook - using the internal Gitea URL
  curl -s --request POST 'http://localhost:7002/webhook' \
    --header 'Content-Type: application/json' \
    --header 'x-webhook-token: xxxxx' \
    --data-raw "{\"gitEvent\":\"git.push\",\"repository\":{\"git_url\":\"$OPAL_POLICY_REPO_URL_FOR_WEBHOOK\"}}"
  sleep 5
  check_clients_logged "PUT /v1/policies/$regofile -> 200"
}

function test_data_publish {
  echo "- Testing data publish for user $1"
  user=$1

  # Use curl to publish data update via OPAL server API
  curl -s -X POST http://localhost:7002/data/config \
    -H "Authorization: Bearer $OPAL_DATA_SOURCE_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{
      "entries": [{
        "url": "https://api.country.is/23.54.6.78",
        "config": {},
        "topics": ["policy_data"],
        "dst_path": "/users/'$user'/location",
        "save_method": "PUT"
      }]
    }'

  sleep 5
  check_clients_logged "PUT /v1/data/users/$user/location -> 204"
}

function test_statistics {
    echo "- Testing statistics feature"
    # Make sure 2 servers & 2 clients (repeat few times cause different workers might response)
    for port in {7002..7003}; do
      for _ in {1..8}; do
        curl -s "http://localhost:${port}/stats" --header "Authorization: Bearer $OPAL_DATA_SOURCE_TOKEN" | grep '"client_count":2,"server_count":2'
      done
    done
}

function main {
  # Ensure we're in the correct directory
  cd "$SCRIPT_DIR"

  # Setup
  generate_opal_keys

  trap clean_up EXIT

  # Bring up containers
  compose down --remove-orphans

  echo "Starting Gitea"
  compose up -d gitea --force-recreate
  sleep 5  # Give Gitea time to start

  echo "Preparing policy repository"
  prepare_policy_repo

  echo "Starting OPAL services"
  # Start OPAL services
  compose up -d --force-recreate
  sleep 15  # Give OPAL more time to start

  # Check containers started correctly
  check_clients_logged "Connected to PubSub server"
  check_clients_logged "Got policy bundle"
  check_clients_logged 'PUT /v1/data/static -> 204'
  check_no_error

  # Test functionality
  test_data_publish "bob"
  test_push_policy "something"
  test_statistics

  echo "- Testing broadcast channel disconnection"
  compose restart broadcast_channel
  sleep 10

  test_data_publish "alice"
  test_push_policy "another"
  test_data_publish "sunil"
  test_data_publish "eve"
  test_push_policy "best_one_yet"
  # TODO: Test statistics feature again after broadcaster restart (should first fix statistics bug)
}

# Retry test in case of failure to avoid flakiness
MAX_RETRIES=5
RETRY_COUNT=0

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
  echo "Running test (attempt $((RETRY_COUNT+1)) of $MAX_RETRIES)..."
  main && break
  RETRY_COUNT=$((RETRY_COUNT + 1))
  echo "Test failed, retrying..."
done

if [ $RETRY_COUNT -ge $MAX_RETRIES ]; then
  echo "Tests failed after $MAX_RETRIES attempts."
  exit 1
fi

echo "Tests passed successfully."
