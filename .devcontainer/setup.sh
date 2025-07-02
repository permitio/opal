#!/bin/bash

if [ -d ".venv" ]; then
  echo "Virtual environment already exists"
else
  python3 -m venv .venv
fi
source .venv/bin/activate

apt-get update && apt-get install -y git

pip install --upgrade pip
pip3 install --user -r requirements.txt

cd tests
pip3 install --user -r requirements.txt

pip install pre-commit
pre-commit install
pre-commit run --all-files
