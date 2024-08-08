#!/bin/bash
set -ex

if [ ! -f "docker-compose-with-everything.yml" ]; then
   echo "did not find compose file - run this script from the 'docker/' directory under opal root!"
   exit
fi

#echo "generating opal crypto keys..."
#ssh-keygen -q -t rsa -b 4096 -m pem -f opal_crypto_key -N ""
#
#echo "saving crypto keys to env vars and removing temp key files..."
#export OPAL_AUTH_PUBLIC_KEY=`cat opal_crypto_key.pub`
#export OPAL_AUTH_PRIVATE_KEY=`cat opal_crypto_key | tr '\n' '_'`
#rm opal_crypto_key.pub opal_crypto_key
#
#echo "generating master token..."
#export OPAL_AUTH_MASTER_TOKEN=`openssl rand -hex 16`
#
#if ! command -v opal-server &> /dev/null
#then
#    echo "opal-server cli was not found, run: 'pip install opal-server'"
#    exit
#fi
#
#if ! command -v opal-client &> /dev/null
#then
#    echo "opal-client cli was not found, run: 'pip install opal-client'"
#    exit
#fi
#
#echo "running OPAL server so we can sign on JWT tokens..."
#OPAL_AUTH_JWT_AUDIENCE=https://api.opal.ac/v1/ OPAL_AUTH_JWT_ISSUER=https://opal.ac/ OPAL_REPO_WATCHER_ENABLED=0 opal-server run &
#
#sleep 2;
#
#echo "obtaining client JWT token..."
#export OPAL_CLIENT_TOKEN=`opal-client obtain-token $OPAL_AUTH_MASTER_TOKEN --type client`
#
#echo "killing opal server..."
#ps -ef | grep opal | grep -v grep | awk '{print $2}' | xargs kill
#
#sleep 5;
#
#echo "Saving your config to .env file..."
#rm -f .env
#echo "OPAL_AUTH_PUBLIC_KEY=\"$OPAL_AUTH_PUBLIC_KEY\"" >> .env
#echo "OPAL_AUTH_PRIVATE_KEY=\"$OPAL_AUTH_PRIVATE_KEY\"" >> .env
#echo "OPAL_AUTH_MASTER_TOKEN=\"$OPAL_AUTH_MASTER_TOKEN\"" >> .env
#echo "OPAL_CLIENT_TOKEN=\"$OPAL_CLIENT_TOKEN\"" >> .env
#echo "OPAL_AUTH_PRIVATE_KEY_PASSPHRASE=\"$OPAL_AUTH_PRIVATE_KEY_PASSPHRASE\"" >> .env
#

export POLICY_REPO_BRANCH
POLICY_REPO_BRANCH=test-$RANDOM$RANDOM
rm -rf ./opal-tests-policy-repo
git clone git@github.com:permitio/opal-tests-policy-repo.git
cd opal-tests-policy-repo
git checkout -b $POLICY_REPO_BRANCH
git push --set-upstream origin $POLICY_REPO_BRANCH
cd -

export POLICY_REPO_SSH_KEY
POLICY_REPO_SSH_KEY=${POLICY_REPO_SSH_KEY:=$(cat ~/.ssh/id_rsa)}

docker compose -f docker-compose-with-everything.yml --env-file .env down --remove-orphans
docker compose -f docker-compose-with-everything.yml --env-file .env up -d
sleep 10

clean_up () {
    ARG=$?
    if [[ "$ARG" -ne 0 ]]; then
#      docker compose -f docker-compose-with-everything.yml logs
      echo "Failed test"
    else
      echo "OK"
    fi
    # TODO: Have an arg for not bringing it down
#    docker compose -f docker-compose-with-everything.yml down
#    rm -rf ./opal-tests-policy-repo
    # TODO: Remove branch
    exit $ARG
}
trap clean_up EXIT

# Test callback worked
docker compose -f docker-compose-with-everything.yml logs --index 1 opal_client | grep -q "Connected to PubSub server"
docker compose -f docker-compose-with-everything.yml logs --index 1 opal_client | grep -q "Got policy bundle"
docker compose -f docker-compose-with-everything.yml logs --index 1 opal_client | grep -q 'PUT /v1/data/static -> 204'
if docker compose -f docker-compose-with-everything.yml logs --index 1 opal_client | grep -q 'ERROR'; then
  echo "Found error in logs"
  exit 1
fi
docker compose -f docker-compose-with-everything.yml logs --index 2 opal_client | grep -q "Connected to PubSub server"
docker compose -f docker-compose-with-everything.yml logs --index 2 opal_client | grep -q "Got policy bundle"
docker compose -f docker-compose-with-everything.yml logs --index 2 opal_client | grep -q 'PUT /v1/data/static -> 204'
if docker compose -f docker-compose-with-everything.yml logs --index 2 opal_client | grep -q 'ERROR'; then
  echo "Found error in logs"
  exit 1
fi


# Git push
# TODO: Turn into a function
cd opal-tests-policy-repo; echo "package something" > something.rego; git add something.rego ; git commit -m "Add something.rego"; git push; cd -
curl --request POST 'http://localhost:7002/webhook' --header 'Content-Type: application/json' --header 'x-webhook-token: xxxxx' --data-raw '{"gitEvent":"git.push","repository":{"git_url":"git@github.com:permitio/opal-tests-policy-repo.git"}}'
sleep 2
docker compose -f docker-compose-with-everything.yml logs --index 1 opal_client | grep -q 'PUT /v1/policies/something.rego -> 200'
docker compose -f docker-compose-with-everything.yml logs --index 2 opal_client | grep -q 'PUT /v1/policies/something.rego -> 200'

### Test data publish
set -o allexport
source .env
set +o allexport

export OPAL_CLIENT_TOKEN
OPAL_CLIENT_TOKEN=$(opal-client obtain-token "$OPAL_AUTH_MASTER_TOKEN" --type datasource)

opal-client publish-data-update --src-url https://api.country.is/23.54.6.78 -t policy_data --dst-path /users/bob/location
sleep 2
docker compose -f docker-compose-with-everything.yml logs --index 1 opal_client | grep -q 'PUT /v1/data/users/bob/location -> 204'
docker compose -f docker-compose-with-everything.yml logs --index 2 opal_client | grep -q 'PUT /v1/data/users/bob/location -> 204'


# TODO: Test statistic

docker compose -f docker-compose-with-everything.yml restart broadcast_channel
sleep 10

# TODO: Maybe do couple of times so this would test different processes handling the request.
opal-client publish-data-update --src-url https://api.country.is/23.54.6.78 -t policy_data --dst-path /users/alice/location
sleep 2
docker compose -f docker-compose-with-everything.yml logs --index 1 opal_client | grep -q 'PUT /v1/data/users/alice/location -> 204'
docker compose -f docker-compose-with-everything.yml logs --index 2 opal_client | grep -q 'PUT /v1/data/users/alice/location -> 204'

# Git push
# TODO: Turn into a function
cd opal-tests-policy-repo; echo "package another" > another.rego; git add another.rego ; git commit -m "Add another.rego"; git push; cd -
curl --request POST 'http://localhost:7002/webhook' --header 'Content-Type: application/json' --header 'x-webhook-token: xxxxx' --data-raw '{"gitEvent":"git.push","repository":{"git_url":"git@github.com:permitio/opal-tests-policy-repo.git"}}'
sleep 5
docker compose -f docker-compose-with-everything.yml logs --index 1 opal_client | grep -q 'PUT /v1/policies/another.rego -> 200'
docker compose -f docker-compose-with-everything.yml logs --index 2 opal_client | grep -q 'PUT /v1/policies/another.rego -> 200'

echo "Success!"
