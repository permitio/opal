#!/bin/bash
set -e

export OPAL_CLIENT_TOKEN
export OPAL_DATA_SOURCE_TOKEN

function test_push_policy {
  echo "- Testing pushing policy $1"
  regofile="$1.rego"
  cd opal-example-policy-repo
  echo "package $1" > "$regofile"
  git add "$regofile"
  git commit -m "Add $regofile"
  git push --set-upstream origin master
  git push
  cd -

  curl -s --request POST 'http://localhost:7002/webhook' --header 'Content-Type: application/json' --header 'x-webhook-token: xxxxx' --data-raw '{"gitEvent":"git.push","repository":{"git_url":"'"$OPAL_POLICY_REPO_URL"'"}}'
  sleep 5
  #check_clients_logged "PUT /v1/policies/$regofile -> 200"
}

function test_data_publish {
  echo "- Testing data publish for user $1"
  user=$1
  OPAL_CLIENT_TOKEN=$OPAL_DATA_SOURCE_TOKEN opal-client publish-data-update --src-url https://api.country.is/23.54.6.78 -t policy_data --dst-path "/users/$user/location"
  sleep 5
  #check_clients_logged "PUT /v1/data/users/$user/location -> 204"
}

function test_statistics {
    echo "- Testing statistics feature"
    # Make sure 2 servers & 2 clients (repeat few times cause different workers might response)
    for _ in {1..10}; do
      curl -s 'http://localhost:7002/stats' --header "Authorization: Bearer $OPAL_DATA_SOURCE_TOKEN" | grep '"client_count":2,"server_count":2'
    done
}

function main {

  # Test functionality
  test_data_publish "bob"
  test_push_policy "something"
  test_statistics

  test_data_publish "alice"
  test_push_policy "another"
  test_data_publish "sunil"
  test_data_publish "eve"
  test_push_policy "best_one_yet"
  # TODO: Test statistics feature again after broadcaster restart (should first fix statistics bug)
}

main
