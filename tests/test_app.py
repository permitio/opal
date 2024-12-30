import asyncio
from datetime import datetime, timezone
import os
import re
import subprocess
import pytest
import requests
import time
from tests.containers.gitea_container import GiteaContainer
from tests.containers.opal_server_container import OpalServerContainer
from tests.containers.opal_client_container import OpalClientContainer
from tests.containers.opal_client_container import PermitContainer

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


OPAL_DISTRIBUTION_TIME = 2
ip_to_location_base_url = "https://api.country.is/"
 
def publish_data_user_location(src, user, opal_server: OpalServerContainer):
    """Publish user location data to OPAL."""
    # Construct the command to publish data update
    publish_data_user_location_command = (
        f"opal-client publish-data-update --server-url http://localhost:{opal_server.settings.port} --src-url {src} "
        f"-t policy_data --dst-path /users/{user}/location {opal_server.obtain_OPAL_tokens()['datasource']}"
    )
    logger.info(publish_data_user_location_command)
    logger.info("test")
    
    # Execute the command
    result = subprocess.run(publish_data_user_location_command, shell=True)
    
    
    input("press enter to continue!")
    # Check command execution result
    if result.returncode != 0:
        logger.error("Error: Failed to update user location!")
    else:
        logger.info(f"Successfully updated user location with source: {src}")
    input("press enter to continue!")


def test_user_location(opal_server: list[OpalServerContainer], opal_client: list[OpalClientContainer]):
    """Test data publishing"""

     # Generate the reference timestamp
    reference_timestamp = datetime.now(timezone.utc)
    logger.info(f"Reference timestamp: {reference_timestamp}")

    # Publish data to the OPAL server
    logger.info(ip_to_location_base_url)
    publish_data_user_location(f"{ip_to_location_base_url}8.8.8.8", "bob", opal_server[0])
    logger.info("Published user location for 'bob'.")

    log_found = opal_client[0].wait_for_log(reference_timestamp, "PUT /v1/data/users/bob/location -> 204", 30)
    logger.info("Finished processing logs.")
    assert log_found, "Expected log entry not found after the reference timestamp."

async def data_publish_and_test(user, allowed_country, locations, opasl_server: OpalServerContainer, opal_client: OpalClientContainer):
    """Run the user location policy tests multiple times."""

    for location in locations:
        ip = location[0]
        user_country = location[1]

        publish_data_user_location(f"{ip_to_location_base_url}{ip}", user, opasl_server)

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
async def test_policy_and_data_updates(gitea_server: GiteaContainer, opal_server: list[OpalServerContainer], opal_client: list[OpalClientContainer], temp_dir):
    """    
    This script updates policy configurations and tests access 
    based on specified settings and locations. It integrates 
    with Gitea and OPA for policy management and testing.
    """
    logger.info("test-0")
    
    # Parse locations into separate lists of IPs and countries
    locations = [("8.8.8.8","US"), ("77.53.31.138","SE")]
    DATASOURCE_TOKEN  = opal_server[0].obtain_OPAL_tokens()["datasource"]

    for location in locations:    
        # Update policy to allow only non-US users
        print(f"Updating policy to allow only users from {location[1]}...")
        update_policy(gitea_server, opal_server[0], location[1])

        assert await data_publish_and_test("bob", location[1], locations, opal_server[0], opal_client[0])

@pytest.mark.parametrize("attempts", [10])  # Number of attempts to repeat the check
def test_read_statistics(attempts, opal_server: list[OpalServerContainer], opal_client: list[OpalClientContainer],
                          number_of_opal_servers: int, number_of_opal_clients: int):
    """
    Tests the statistics feature by verifying the number of clients and servers.
    """
    print("- Testing statistics feature")
 
    time.sleep(15)

    for server in opal_server:
        print(f"OPAL Server: {server.settings.container_name}:{server.settings.port}")

        # The URL for statistics
        stats_url = f"http://localhost:{server.settings.port}/stats"

        headers = {"Authorization": f"Bearer {server.obtain_OPAL_tokens()['datasource']}"}

        # Repeat the request multiple times
        for attempt in range(attempts):
            print(f"Attempt {attempt + 1}/{attempts} - Checking statistics...")

            try:
                time.sleep(1)
                # Send a request to the statistics endpoint
                response = requests.get(stats_url, headers=headers)
                response.raise_for_status()  # Raise an error for HTTP status codes 4xx/5xx

                print(f"Response: {response.status_code} {response.text}")

                # Look for the expected data in the response
                stats = utils.get_client_and_server_count(response.text)
                if stats is None:
                    pytest.fail(f"Expected statistics not found in response: {response.text}")

                client_count = stats["client_count"]
                server_count = stats["server_count"]  
                print(f"Number of OPAL servers expected: {number_of_opal_servers}, found: {server_count}")
                print(f"Number of OPAL clients expected: {number_of_opal_clients}, found: {client_count}")

                if(server_count < number_of_opal_servers):
                    pytest.fail(f"Expected number of servers not found in response: {response.text}")

                if(client_count < number_of_opal_clients):
                    pytest.fail(f"Expected number of clients not found in response: {response.text}")

            except requests.RequestException as e:
                if response is not None:
                    print(f"Request failed: {response.status_code} {response.text}")
                pytest.fail(f"Failed to fetch statistics: {e}")

    print("Statistics check passed in all attempts.")

@pytest.mark.asyncio
async def test_policy_update(gitea_server: GiteaContainer, opal_server: list[OpalServerContainer], opal_client: list[OpalClientContainer], temp_dir):
    # Parse locations into separate lists of IPs and countries
    location = "CN"

     # Generate the reference timestamp
    reference_timestamp = datetime.now(timezone.utc)
    logger.info(f"Reference timestamp: {reference_timestamp}")


    # Update policy to allow only non-US users
    print(f"Updating policy to allow only users from {location}...")
    update_policy(gitea_server, opal_server[0], "location")

    log_found = opal_server[0].wait_for_log(reference_timestamp, "Found new commits: old HEAD was", 30)
    logger.info("Finished processing logs.")
    assert log_found, "Expected log entry not found after the reference timestamp."


    log_found = opal_client[0].wait_for_log(reference_timestamp, "Fetching policy bundle from", 30)
    logger.info("Finished processing logs.")
    assert log_found, "Expected log entry not found after the reference timestamp."

def test_with_statistics_disabled(opal_server: list[OpalServerContainer]):
    assert False

def test_with_uvicorn_workers_and_no_broadcast_channel(opal_server: list[OpalServerContainer]):
    assert False