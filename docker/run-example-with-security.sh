#!/bin/bash
#
# Runs the docker-compose-with-security.yml example with
# crypto keys configured via environment variables
#
# Usage:
#
# $ ./run-example-with-security.sh
#

set -e

if [ ! -f "docker-compose-with-security.yml" ]; then
   echo "did not find compose file - run this script from the 'docker/' directory under opal root!"
   exit
fi

echo "------------------------------------------------------------------"
echo "This script will run the docker-compose-with-security.yml example"
echo "configuration, and demonstrates how to correctly generate crypto"
echo "keys and run OPAL in *secure mode*."
echo "------------------------------------------------------------------"

echo "generating opal crypto keys..."
ssh-keygen -q -t rsa -b 4096 -m pem -f opal_crypto_key -N ""

echo "saving crypto keys to env vars and removing temp key files..."
export OPAL_AUTH_PUBLIC_KEY=`cat opal_crypto_key.pub`
export OPAL_AUTH_PRIVATE_KEY=`cat opal_crypto_key | tr '\n' '_'`
rm opal_crypto_key.pub opal_crypto_key

echo "generating master token..."
export OPAL_AUTH_MASTER_TOKEN=`openssl rand -hex 16`

if ! command -v opal-server &> /dev/null
then
    echo "opal-server cli was not found, run: 'pip install opal-server'"
    exit
fi

if ! command -v opal-client &> /dev/null
then
    echo "opal-client cli was not found, run: 'pip install opal-client'"
    exit
fi

echo "running OPAL server so we can sign on JWT tokens..."
OPAL_AUTH_JWT_AUDIENCE=https://api.opal.ac/v1/ OPAL_AUTH_JWT_ISSUER=https://opal.ac/ OPAL_REPO_WATCHER_ENABLED=0 opal-server run &

sleep 2;

echo "obtaining client JWT token..."
export OPAL_CLIENT_TOKEN=`opal-client obtain-token $OPAL_AUTH_MASTER_TOKEN --type client`

echo "killing opal server..."
ps -ef | grep opal | grep -v grep | awk '{print $2}' | xargs kill

sleep 5;

echo "Saving your config to .env file..."
rm -f .env
echo "OPAL_AUTH_PUBLIC_KEY=\"$OPAL_AUTH_PUBLIC_KEY\"" >> .env
echo "OPAL_AUTH_PRIVATE_KEY=\"$OPAL_AUTH_PRIVATE_KEY\"" >> .env
echo "OPAL_AUTH_MASTER_TOKEN=\"$OPAL_AUTH_MASTER_TOKEN\"" >> .env
echo "OPAL_CLIENT_TOKEN=\"$OPAL_CLIENT_TOKEN\"" >> .env
echo "OPAL_AUTH_PRIVATE_KEY_PASSPHRASE=\"$OPAL_AUTH_PRIVATE_KEY_PASSPHRASE\"" >> .env

echo "--------"
echo "ready to run..."
echo "--------"

docker compose -f docker-compose-with-security.yml --env-file .env up --force-recreate
