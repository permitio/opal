#!/bin/bash
set -e

if [[ -f ".env" ]]; then
  # shellcheck disable=SC1091
  source .env
fi

function cleanup {
  rm -rf ./opal-tests-policy-repo

  PATTERN="pytest_[a-f,0-9]*.env"
  echo "Looking for auto-generated .env files matching pattern '$PATTERN'..."

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

function main {

  # Cleanup before starting, maybe some leftovers from previous runs
  cleanup

  echo "Running tests..."

  # Check if a specific test is provided
  if [[ -n "$1" ]]; then
    echo "Running specific test: $1"
    python -Xfrozen_modules=off -m debugpy --listen 5678 -m pytest -s "$1"
  else
    echo "Running all tests..."
    python -Xfrozen_modules=off -m debugpy --listen 5678 -m pytest -s
  fi

  echo "Done!"

  # Cleanup at the end
  cleanup
}

main "$@"
