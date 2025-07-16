#!/bin/bash
set -e

export OPAL_AUTH_PUBLIC_KEY
export OPAL_AUTH_PRIVATE_KEY
export OPAL_AUTH_MASTER_TOKEN
export OPAL_CLIENT_TOKEN
export OPAL_DATA_SOURCE_TOKEN

function generate_opal_keys {
  echo "- Generating OPAL keys"

  ssh-keygen -q -t rsa -b 4096 -m pem -f opal_crypto_key -N ""
  OPAL_AUTH_PUBLIC_KEY="$(cat opal_crypto_key.pub)"
  OPAL_AUTH_PRIVATE_KEY="$(tr '\n' '_' < opal_crypto_key)"
  rm opal_crypto_key.pub opal_crypto_key

  OPAL_AUTH_MASTER_TOKEN="$(openssl rand -hex 16)"
  OPAL_AUTH_JWT_AUDIENCE=https://api.opal.ac/v1/ OPAL_AUTH_JWT_ISSUER=https://opal.ac/ OPAL_REPO_WATCHER_ENABLED=0 \
    opal-server run &
  sleep 2;

  OPAL_CLIENT_TOKEN="$(opal-client obtain-token "$OPAL_AUTH_MASTER_TOKEN" --type client)"
  echo "Client token: $OPAL_CLIENT_TOKEN"
  OPAL_DATA_SOURCE_TOKEN="$(opal-client obtain-token "$OPAL_AUTH_MASTER_TOKEN" --type datasource)"
    # shellcheck disable=SC2009ß
  ps -ef | grep opal-server | grep -v grep | awk '{print $2}' | xargs kill
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
  echo "- Clone tests policy repo to create test's branch"
  export OPAL_POLICY_REPO_URL
  OPAL_POLICY_REPO_URL=${OPAL_POLICY_REPO_URL:-git@github.com:permitio/opal-example-policy-repo.git}

echo "- Forking the policy repo"
OPAL_TARGET_ACCOUNT="SomeTargetAccount" # Replace with your GitHub username
ORIGINAL_REPO_NAME=$(basename -s .git "$OPAL_POLICY_REPO_URL")
NEW_REPO_NAME="${ORIGINAL_REPO_NAME}"
FORKED_REPO_URL="git@github.com:${OPAL_TARGET_ACCOUNT}/${NEW_REPO_NAME}.git"

# Check if the forked repository already exists
if gh repo list "$OPAL_TARGET_ACCOUNT" --json name -q '.[].name' | grep -q "^${NEW_REPO_NAME}$"; then
  echo "Forked repository $NEW_REPO_NAME already exists."
  OPAL_POLICY_REPO_URL="$FORKED_REPO_URL"
  echo "Using existing forked repository: $OPAL_POLICY_REPO_URL"
else
  # Using GitHub CLI to fork the repository
  # gh repo fork "$OPAL_POLICY_REPO_URL" --clone --remote=false --org="$OPAL_TARGET_ACCOUNT"
  OPAL_TARGET_PAT="${pat:-}"
  curl -X POST -H "Authorization: token $OPAL_TARGET_PAT" https://api.github.com/repos/permitio/opal-example-policy-repo/forks
  if [ $? -eq 0 ]; then
    echo "Fork created successfully!"
  else
    echo "Error creating fork: $?"
  fi

  # Update OPAL_POLICY_REPO_URL to point to the forked repo
  OPAL_POLICY_REPO_URL="$FORKED_REPO_URL"
  echo "Updated OPAL_POLICY_REPO_URL to $OPAL_POLICY_REPO_URL"
fi


  export POLICY_REPO_BRANCH
  POLICY_REPO_BRANCH=test-$RANDOM$RANDOM
  rm -rf ./opal-example-policy-repo
  git clone "$OPAL_POLICY_REPO_URL"
  cd opal-example-policy-repo
  git checkout -b $POLICY_REPO_BRANCH
  git push --set-upstream origin $POLICY_REPO_BRANCH
  cd -

  echo "OPAL_POLICY_REPO_URL=\"$OPAL_POLICY_REPO_URL\"" >> .env
  echo "POLICY_REPO_BRANCH=\"$POLICY_REPO_BRANCH\"" >> .env

  # That's for the docker-compose to use, set ssh key from "~/.ssh/id_rsa", unless another path/key data was configured
  export OPAL_POLICY_REPO_SSH_KEY
  OPAL_POLICY_REPO_SSH_KEY_PATH=${OPAL_POLICY_REPO_SSH_KEY_PATH:-~/.ssh/id_rsa}
  OPAL_POLICY_REPO_SSH_KEY=${OPAL_POLICY_REPO_SSH_KEY:-$(cat "$OPAL_POLICY_REPO_SSH_KEY_PATH")}
  echo "- OPAL_POLICY_REPO_SSH_KEY=$OPAL_POLICY_REPO_SSH_KEY"
  echo "OPAL_POLICY_REPO_SSH_KEY=\"$OPAL_POLICY_REPO_SSH_KEY\"" >> .env
}

function compose {
  docker compose -f ./docker-compose-app-tests.yml --env-file .env "$@"
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
    #cd opal-example-policy-repo; git push -d origin $POLICY_REPO_BRANCH; cd - # Remove remote tests branch
    rm -rf ./opal-example-policy-repo
    exit $ARG
}

function main {

  generate_opal_keys
  prepare_policy_repo

  trap clean_up EXIT

}

# This script is good if you want to just generate opal keys and initialize the policy repo on your github account
#   and then run some docker compose and tests.
main
