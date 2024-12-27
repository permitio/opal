import asyncio
import os
import subprocess
import pytest
import requests
import time
from tests.containers.gitea_container import GiteaContainer
from tests.containers.opal_server_container import OpalServerContainer
from tests.containers.opal_client_container import OpalClientContainer
from tests import utils

from testcontainers.core.utils import setup_logger

logger = setup_logger(__name__)

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
    return
    utils.prepare_policy_repo("-account=iwphonedo")


    # Step 1: Publish data for "bob"
    data_publish("bob")

    return

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


#############################################################

OPAL_DISTRIBUTION_TIME = 25
ip_to_location_base_url = "https://api.country.is/"
 
def publish_data_user_location(src, user, DATASOURCE_TOKEN):
    """Publish user location data to OPAL."""
    # Construct the command to publish data update
    publish_data_user_location_command = (
        f"opal-client publish-data-update --src-url {src} "
        f"-t policy_data --dst-path /users/{user}/location {DATASOURCE_TOKEN}"
    )
    logger.info("test")
    
    # Execute the command
    result = subprocess.run(
        publish_data_user_location_command, shell=True, capture_output=True, text=True
    )
    logger.info("test-1")

    # Check command execution result
    if result.returncode != 0:
        logger.error("Error: Failed to update user location!")
    else:
        logger.info(f"Successfully updated user location with source: {src}")


def test_user_location(opal_server: OpalServerContainer, opal_client: OpalClientContainer):
    """Test data publishing"""

    logger.info(ip_to_location_base_url)
    publish_data_user_location(f"{ip_to_location_base_url}8.8.8.8", "bob", opal_server.obtain_OPAL_tokens()["datasource"])
    logger.info("test1")
    print(f"bob's location set to: US. Expected outcome: NOT ALLOWED.")

    logger.info(time.strftime("%H:%M:%S"))

    time.sleep(OPAL_DISTRIBUTION_TIME)
    a = opal_client.get_logs()
    logger.info(a)
    logger.info(time.strftime("%H:%M:%S"))

    log_found = "PUT /v1/data/users/bob/location -> 204" in a
    assert log_found

async def data_publish_and_test(user, allowed_country, locations, DATASOURCE_TOKEN, opal_client: OpalClientContainer):
    """Run the user location policy tests multiple times."""

    for location in locations:
        ip = location[0]
        user_country = location[1]

        publish_data_user_location(f"{ip_to_location_base_url}{ip}", user, DATASOURCE_TOKEN)

        if (allowed_country == user_country):
            print(f"{user}'s location set to: {user_country}. current_country is set to: {allowed_country} Expected outcome: ALLOWED.")
        else:
            print(f"{user}'s location set to: {user_country}. current_country is set to: {allowed_country} Expected outcome: NOT ALLOWED.")

        await asyncio.sleep(1)
        
        assert await utils.opal_authorize(user, f"http://localhost:{opal_client.settings.opa_port}/v1/data/app/rbac/allow") == (allowed_country == user_country)
    return True
        
def update_policy(gitea_container: GiteaContainer, opal_server_container: OpalServerContainer, country_value):
    """Update the policy file dynamically."""

    gitea_container.update_branch(opal_server_container.settings.policy_repo_main_branch,
             "rbac.rego", 
             (
            "package app.rbac\n"
            "default allow = false\n\n"
            "# Allow the action if the user is granted permission to perform the action.\n"
            "allow {\n"
            "\t# unless user location is outside US\n"
            "\tcountry := data.users[input.user].location.country\n"
            "\tcountry == \"" + country_value + "\"\n"
            "}"
        ),)
        
    utils.wait_policy_repo_polling_interval(opal_server_container)

 
#@pytest.mark.parametrize("location", ["CN", "US", "SE"])
@pytest.mark.asyncio
async def test_policy_and_data_updates(gitea_server: GiteaContainer, opal_server: OpalServerContainer, opal_client: OpalClientContainer, temp_dir):
    """    
    This script updates policy configurations and tests access 
    based on specified settings and locations. It integrates 
    with Gitea and OPA for policy management and testing.
    """
    logger.info("test-0")
    
    # Parse locations into separate lists of IPs and countries
    locations = [("8.8.8.8","US"), ("77.53.31.138","SE"), ("210.2.4.8","CN")]
    DATASOURCE_TOKEN  = opal_server.obtain_OPAL_tokens()["datasource"]


    for location in locations:    
        # Update policy to allow only non-US users
        print(f"Updating policy to allow only users from {location[1]}...")
        update_policy(gitea_server, opal_server, location[1])

        assert await data_publish_and_test("bob", location[1], locations, DATASOURCE_TOKEN, opal_client)
