import os
import subprocess
import pytest
import requests
import time
import utils

# TODO: Replace once all fixtures are properly working.
def test_trivial():
    assert 4 + 1 == 5

#@pytest.mark.parametrize("policy_name", ["something"])  # Add more users as needed
def push_policy(policy_name):
    """
    Test pushing a policy by simulating creating, committing, and pushing a policy file,
    and triggering a webhook.
    """
    print(f"- Testing pushing policy {policy_name}")
    regofile = f"{policy_name}.rego"
    opal_repo_path = "opal-tests-policy-repo"
    
    try:
        # Change to the policy repository directory
        os.chdir(opal_repo_path)
        
        # Create a .rego file with the policy name as the package
        with open(regofile, "w") as f:
            f.write(f"package {policy_name}\n")
        
        # Run Git commands to add, commit, and push the policy file
        subprocess.run(["git", "add", regofile], check=True)
        subprocess.run(["git", "commit", "-m", f"Add {regofile}"], check=True)
        subprocess.run(["git", "push"], check=True)
    finally:
        # Change back to the previous directory
        os.chdir("..")
    
    # Trigger the webhook
    webhook_url = "http://localhost:7002/webhook"
    webhook_headers = {
        "Content-Type": "application/json",
        "x-webhook-token": "xxxxx"
    }
    webhook_payload = {
        "gitEvent": "git.push",
        "repository": {
            "git_url": os.environ.get("OPAL_POLICY_REPO_URL", "")
        }
    }
    
    response = requests.post(webhook_url, headers=webhook_headers, json=webhook_payload)
    if response.status_code != 200:
        print(f"Webhook POST failed: {response.status_code} {response.text}")
    else:
        print("Webhook POST succeeded")
    
    # Wait for a few seconds to allow changes to propagate
    time.sleep(5)
    
    # Check client logs (Placeholder: replace with actual logic to check logs)
    utils.check_clients_logged(f"PUT /v1/policies/{regofile} -> 200")

#@pytest.mark.parametrize("user", ["user1", "user2"])  # Add more users as needed
def data_publish(user):
    """
    Tests data publishing for a given user.
    """
    print(f"- Testing data publish for user {user}")
    
    # Set the required environment variable
    opal_client_token = "OPAL_DATA_SOURCE_TOKEN_VALUE"  # Replace with the actual token value
    
    # Run the `opal-client publish-data-update` command
    command = [
        "opal-client", 
        "publish-data-update", 
        "--src-url", "https://api.country.is/23.54.6.78",
        "-t", "policy_data", 
        "--dst-path", f"/users/{user}/location"
    ]
    env = os.environ.copy()
    env["OPAL_CLIENT_TOKEN"] = opal_client_token

    result = subprocess.run(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    if result.returncode != 0:
        pytest.fail(f"opal-client command failed: {result.stderr.strip()}")
    
    # Wait for the operation to complete
    time.sleep(5)
    
    # Check logs for the expected message
    log_message = f"PUT /v1/data/users/{user}/location -> 204"
    utils.check_clients_logged(log_message)


#@pytest.mark.parametrize("attempts", [10])  # Number of attempts to repeat the check
def read_statistics(attempts):
    """
    Tests the statistics feature by verifying the number of clients and servers.
    """
    print("- Testing statistics feature")

    # Set the required Authorization token
    token = "OPAL_DATA_SOURCE_TOKEN_VALUE"  # Replace with the actual token value

    # The URL for statistics
    stats_url = "http://localhost:7002/stats"

    headers = {"Authorization": f"Bearer {token}"}

    # Repeat the request multiple times
    for attempt in range(attempts):
        print(f"Attempt {attempt + 1}/{attempts} - Checking statistics...")

        try:
            # Send a request to the statistics endpoint
            response = requests.get(stats_url, headers=headers)
            response.raise_for_status()  # Raise an error for HTTP status codes 4xx/5xx

            # Look for the expected data in the response
            if '"client_count":2,"server_count":2' not in response.text:
                pytest.fail(f"Expected statistics not found in response: {response.text}")

        except requests.RequestException as e:
            pytest.fail(f"Failed to fetch statistics: {e}")

    print("Statistics check passed in all attempts.")

def test_sequence():
    """
    Executes a sequence of tests:
    - Publishes data updates for various users
    - Pushes different policies
    - Verifies statistics
    - Tests the broadcast channel reconnection
    """
    print("Starting test sequence...")

    utils.prepare_policy_repo("-account=iwphonedo")

    return

    # Step 1: Publish data for "bob"
    data_publish("bob")


    # Step 2: Push a policy named "something"
    push_policy("something")

    # Step 3: Verify statistics
    read_statistics()

    # Step 4: Restart the broadcast channel and verify reconnection
    print("- Testing broadcast channel disconnection")
    utils.compose("restart", "broadcast_channel")  # Restart the broadcast channel
    time.sleep(10)  # Wait for the channel to restart

    # Step 5: Publish data and push more policies
    data_publish("alice")
    push_policy("another")
    data_publish("sunil")
    data_publish("eve")
    push_policy("best_one_yet")

    print("Test sequence completed successfully.")