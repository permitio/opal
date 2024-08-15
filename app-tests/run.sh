#!/bin/bash
set -e

export OPAL_AUTH_PUBLIC_KEY
export OPAL_AUTH_PRIVATE_KEY
export OPAL_AUTH_MASTER_TOKEN
export OPAL_CLIENT_TOKEN
export OPAL_DATA_SOURCE_TOKEN

function generate_opal_keys {
  echo "generating OPAL keys"

  ssh-keygen -q -t rsa -b 4096 -m pem -f opal_crypto_key -N ""
  OPAL_AUTH_PUBLIC_KEY="$(cat opal_crypto_key.pub)"
  OPAL_AUTH_PRIVATE_KEY="$(tr '\n' '_' < opal_crypto_key)"
  rm opal_crypto_key.pub opal_crypto_key

  OPAL_AUTH_MASTER_TOKEN="$(openssl rand -hex 16)"
  OPAL_AUTH_JWT_AUDIENCE=https://api.opal.ac/v1/ OPAL_AUTH_JWT_ISSUER=https://opal.ac/ OPAL_REPO_WATCHER_ENABLED=0 opal-server run &
  sleep 2;
  OPAL_CLIENT_TOKEN="$(opal-client obtain-token "$OPAL_AUTH_MASTER_TOKEN" --type client)"
  OPAL_DATA_SOURCE_TOKEN="$(opal-client obtain-token "$OPAL_AUTH_MASTER_TOKEN" --type datasource)"
  pkill opal
  sleep 5;

  echo "create .env file"
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
  echo "clone tests policy repo to create test's branch"
  export POLICY_REPO_BRANCH
  POLICY_REPO_BRANCH=test-$RANDOM$RANDOM
  rm -rf ./opal-tests-policy-repo
  git clone git@github.com:permitio/opal-tests-policy-repo.git
  cd opal-tests-policy-repo
  git checkout -b $POLICY_REPO_BRANCH
  git push --set-upstream origin $POLICY_REPO_BRANCH
  cd -

  export OPAL_POLICY_REPO_SSH_KEY
  OPAL_POLICY_REPO_SSH_KEY=$(cat "$POLICY_REPO_SSH_KEY_PATH")
}

# Test setup
generate_opal_keys
prepare_policy_repo

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
    echo "Found error in logs"
    exit 1
  fi
}

function clean_up {
    ARG=$?
    if [[ "$ARG" -ne 0 ]]; then
      echo "*** Test Failed ***"
      echo ""
      compose logs
    else
      echo "*** Test Passed ***"
      echo ""
    fi
    compose down
    cd opal-tests-policy-repo; git push -d origin $POLICY_REPO_BRANCH; cd - # Remove remote tests branch
    rm -rf ./opal-tests-policy-repo
    exit $ARG
}
trap clean_up EXIT

compose down --remove-orphans
compose up -d
sleep 10

# Check containers started correctly
check_clients_logged "Connected to PubSub server"
check_clients_logged "Got policy bundle"
check_clients_logged 'PUT /v1/data/static -> 204'
check_no_error

function test_push_policy {
  echo "- Testing pushing policy $1"
  regofile="$1.rego"
  cd opal-tests-policy-repo
  echo "package $1" > "$regofile"
  git add "$regofile"
  git commit -m "Add $regofile"
  git push
  cd -

  curl --request POST 'http://localhost:7002/webhook' --header 'Content-Type: application/json' --header 'x-webhook-token: xxxxx' --data-raw '{"gitEvent":"git.push","repository":{"git_url":"git@github.com:permitio/opal-tests-policy-repo.git"}}'
  sleep 5
  check_clients_logged "PUT /v1/policies/$regofile -> 200"
}

function test_data_publish {
  echo "- Testing data publish for user $1"
  user=$1
  OPAL_CLIENT_TOKEN=$OPAL_DATA_SOURCE_TOKEN opal-client publish-data-update --src-url https://api.country.is/23.54.6.78 -t policy_data --dst-path "/users/$user/location"
  sleep 5
  check_clients_logged "PUT /v1/data/users/$user/location -> 204"
}

test_data_publish "bob"
test_push_policy "something"

# TODO: Test statistic

echo "- Testing broadcast channel disconnection"
compose restart broadcast_channel
sleep 10

test_data_publish "alice"
test_push_policy "another"

test_data_publish "sunil"
test_data_publish "eve"
test_push_policy "best_one_yet"
