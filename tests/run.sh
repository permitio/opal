#!/bin/bash
set -e

if [[ -f ".env" ]]; then
  # shellcheck disable=SC1091
  source .env
fi

# TODO: Disable after debugging.
export OPAL_TESTS_DEBUG='true'
export OPAL_POLICY_REPO_URL
export OPAL_POLICY_REPO_MAIN_BRANCH
export OPAL_POLICY_REPO_SSH_KEY
export OPAL_AUTH_PUBLIC_KEY
export OPAL_AUTH_PRIVATE_KEY

#OPAL_POLICY_REPO_URL=${OPAL_POLICY_REPO_URL:-git@github.com:permitio/opal-tests-policy-repo.git}
OPAL_POLICY_REPO_URL=${OPAL_POLICY_REPO_URL:-git@github.com:iwphonedo/opal-example-policy-repo.git}
#OPAL_POLICY_REPO_MAIN_BRANCH=test-$RANDOM$RANDOM
OPAL_POLICY_REPO_MAIN_BRANCH=master
OPAL_POLICY_REPO_SSH_KEY_PATH=${OPAL_POLICY_REPO_SSH_KEY_PATH:-~/.ssh/id_rsa}
OPAL_POLICY_REPO_SSH_KEY=${OPAL_POLICY_REPO_SSH_KEY:-$(cat "$OPAL_POLICY_REPO_SSH_KEY_PATH")}

function cleanup {
  
  rm -rf ./opal-tests-policy-repo

  # Define the pattern for pytest-generated .env files
  PATTERN="pytest_[a-f,0-9]*.env"

  echo "Looking for auto-generated .env files matching pattern '$PATTERN'..."

  # Iterate over matching files and delete them
  for file in $PATTERN; do
    if [[ -f "$file" ]]; then
      echo "Deleting file: $file"
      rm "$file"
    else
      echo "No matching files found for pattern '$PATTERN'."
      break
    fi
  done

  echo "Cleanup complete!\n"
}
function generate_opal_keys {
  echo "- Generating OPAL keys"

  ssh-keygen -q -t rsa -b 4096 -m pem -f opal_crypto_key -N ""
  OPAL_AUTH_PUBLIC_KEY="$(cat opal_crypto_key.pub)"
  OPAL_AUTH_PRIVATE_KEY="$(tr '\n' '_' <opal_crypto_key)"
  rm opal_crypto_key.pub opal_crypto_key
  
  echo "- OPAL keys generated\n"
}

function install_opal_server_and_client {
  echo "- Installing opal-server and opal-client from pip..."

  pip install opal-server opal-client
  
  if ! command -v opal-server &> /dev/null || ! command -v opal-client &> /dev/null; then
    echo "Installation failed: opal-server or opal-client is not available."
    exit 1
  fi

  echo "- opal-server and opal-client successfully installed."
}

function main {
  
  # Cleanup before starting, maybe some leftovers from previous runs
  cleanup
  
  # Setup
  generate_opal_keys

  # Install opal-server and opal-client
  install_opal_server_and_client
  
  echo "Running tests..."

  # pytest -s
  python  -Xfrozen_modules=off -m debugpy --listen 5678 -m pytest -s

  echo "Done!"

  # Cleanup at the end
  cleanup
}

main