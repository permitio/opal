#!/bin/bash
set -e

if [[ -f ".env" ]]; then
  # shellcheck disable=SC1091
  source .env
fi

function main {

  echo "Running tests..."

  # Check if a specific test is provided
  if [[ -n "$1" ]]; then
    echo "Running specific test: $1"
    python -Xfrozen_modules=off -m debugpy --listen 5678 -m pytest -s "$@"
  else
    echo "Running all tests..."
    python -Xfrozen_modules=off -m debugpy --listen 5678 -m pytest -s
  fi

  echo "Done!"
}

main "$@"
