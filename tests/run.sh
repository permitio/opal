#!/bin/bash
set -e

if [[ -f ".env" ]]; then
  # shellcheck disable=SC1091
  source .env
fi

# TODO: Disable after debugging.
export OPAL_TESTS_DEBUG='true'
export OPAL_POLICY_REPO_URL
export OPAL_POLICY_REPO_BRANCH
export OPAL_POLICY_REPO_SSH_KEY
export OPAL_AUTH_PUBLIC_KEY
export OPAL_AUTH_PRIVATE_KEY

OPAL_POLICY_REPO_URL=${OPAL_POLICY_REPO_URL:-git@github.com:permitio/opal-tests-policy-repo.git}
OPAL_POLICY_REPO_BRANCH=test-$RANDOM$RANDOM
OPAL_POLICY_REPO_SSH_KEY_PATH=${OPAL_POLICY_REPO_SSH_KEY_PATH:-~/.ssh/id_rsa}
OPAL_POLICY_REPO_SSH_KEY=${OPAL_POLICY_REPO_SSH_KEY:-$(cat "$OPAL_POLICY_REPO_SSH_KEY_PATH")}

function generate_opal_keys {
  echo "- Generating OPAL keys"

  ssh-keygen -q -t rsa -b 4096 -m pem -f opal_crypto_key -N ""
  OPAL_AUTH_PUBLIC_KEY="$(cat opal_crypto_key.pub)"
  OPAL_AUTH_PRIVATE_KEY="$(tr '\n' '_' <opal_crypto_key)"
  rm opal_crypto_key.pub opal_crypto_key
}

function main {
  # Setup
  generate_opal_keys

  pytest -s
}

main