import asyncio
import subprocess
import time
from datetime import datetime, timezone
from typing import List

import pytest
import requests
from testcontainers.core.utils import setup_logger

from tests import utils
from tests.containers.broadcast_container_base import BroadcastContainerBase
from tests.containers.gitea_container import GiteaContainer
from tests.containers.opal_client_container import OpalClientContainer, PermitContainer
from tests.containers.opal_server_container import OpalServerContainer
from tests.policy_repos.policy_repo_factory import SupportedPolicyRepo
from tests.settings import PyTestSessionSettings

logger = setup_logger(__name__)

OPAL_DISTRIBUTION_TIME_SECONDS = 2
ip_to_location_base_url = "https://api.country.is/"


def publish_data_user_location(
    src, user, DATASOURCE_TOKEN: str, port: int, topics: str = "policy_data"
):
    """Publish user location data to OPAL."""
    # Construct the command to publish data update
    publish_data_user_location_command = (
        f"opal-client publish-data-update --server-url http://localhost:{port} --src-url {src} "
        f"-t {topics} --dst-path /users/{user}/location {DATASOURCE_TOKEN}"
    )

    # Execute the command
    result = subprocess.run(publish_data_user_location_command, shell=True)
    # Check command execution result
    if result.returncode != 0:
        logger.error("Error: Failed to update user location!")
    else:
        logger.info(f"Successfully updated user location with source: {src}")


async def data_publish_and_test(
    user,
    allowed_country,
    locations,
    DATASOURCE_TOKEN: str,
    opal_client: OpalClientContainer,
    port: int,
):
    """Run the user location policy tests multiple times."""

    for location in locations:
        ip = location[0]
        user_country = location[1]

        publish_data_user_location(
            f"{ip_to_location_base_url}{ip}", user, DATASOURCE_TOKEN, port
        )

        if allowed_country == user_country:
            print(
                f"{user}'s location set to: {user_country}. current_country is set to: {allowed_country} Expected outcome: ALLOWED."
            )
        else:
            print(
                f"{user}'s location set to: {user_country}. current_country is set to: {allowed_country} Expected outcome: NOT ALLOWED."
            )

        await asyncio.sleep(1)

        assert await utils.opal_authorize(
            user,
            f"http://localhost:{opal_client.settings.opa_port}/v1/data/app/rbac/allow",
        ) == (allowed_country == user_country)
    return True


def update_policy(
    gitea_container: GiteaContainer,
    opal_server_container: OpalServerContainer,
    country_value,
):
    """Update the policy file dynamically."""

    gitea_container.update_branch(
        opal_server_container.settings.policy_repo_main_branch,
        "rbac.rego",
        (
            "package app.rbac\n"
            "default allow = false\n\n"
            "# Allow the action if the user is granted permission to perform the action.\n"
            "allow {\n"
            "\t# unless user location is outside US\n"
            "\tcountry := data.users[input.user].location.country\n"
            '\tcountry == "' + country_value + '"\n'
            "}"
        ),
    )

    utils.wait_policy_repo_polling_interval(opal_server_container)


def test_topiced_user_location(
    opal_servers: list[OpalServerContainer],
    topiced_clients: dict[str, OpalClientContainer],
):
    """Test data publishing."""

    for topic, clients in topiced_clients.items():
        # Generate the reference timestamp
        reference_timestamp = datetime.now(timezone.utc)
        logger.info(f"Reference timestamp: {reference_timestamp}")

        # Publish data to the OPAL server
        publish_data_user_location(
            f"{ip_to_location_base_url}8.8.8.8",
            "bob",
            opal_servers[0].obtain_OPAL_tokens()["datasource"],
            opal_servers[0].settings.port,
            topic,
        )

        logger.info(f"Published user location for 'bob'. | topic: {topic}")

        for client in clients:
            log_found = client.wait_for_log(
                "PUT /v1/data/users/bob/location -> 204", 30, reference_timestamp
            )
            logger.info("Finished processing logs.")
            assert (
                log_found
            ), "Expected log entry not found after the reference timestamp."


from settings import session_matrix


# @pytest.mark.parametrize("session_matrix", list(PyTestSessionSettings())) #, indirect=True)
def test_matrix(session_matrix):
    logger.info(session_matrix["broadcaster"])
    logger.info(session_matrix["mode"])
    logger.info(session_matrix["repo_provider"])


def test_matrix2(session_matrix):
    logger.info(session_matrix["broadcaster"])
    logger.info(session_matrix["mode"])
    logger.info(session_matrix["repo_provider"])


def test_user_location(
    opal_servers: list[OpalServerContainer],
    connected_clients: list[OpalClientContainer],
    session_matrix: PyTestSessionSettings,
):
    """Test data publishing."""

    # Generate the reference timestamp
    reference_timestamp = datetime.now(timezone.utc)
    logger.info(f"Reference timestamp: {reference_timestamp}")

    # Publish data to the OPAL server
    logger.info(ip_to_location_base_url)
    publish_data_user_location(
        f"{ip_to_location_base_url}8.8.8.8",
        "bob",
        opal_servers[0].obtain_OPAL_tokens()["datasource"],
        opal_servers[0].settings.port,
    )
    logger.info("Published user location for 'bob'.")

    for client in connected_clients:
        log_found = client.wait_for_log(
            "PUT /v1/data/users/bob/location -> 204", 30, reference_timestamp
        )
        logger.info("Finished processing logs.")
        assert log_found, "Expected log entry not found after the reference timestamp."


# @pytest.mark.parametrize("location", ["CN", "US", "SE"])
@pytest.mark.asyncio
async def test_policy_and_data_updates(
    gitea_server: GiteaContainer,
    opal_servers: list[OpalServerContainer],
    opal_clients: list[OpalClientContainer],
    temp_dir,
):
    """This script updates policy configurations and tests access based on
    specified settings and locations.

    It integrates with Gitea and OPA for policy management and testing.
    """

    # Parse locations into separate lists of IPs and countries
    locations = [("8.8.8.8", "US"), ("77.53.31.138", "SE")]
    for server in opal_servers:
        DATASOURCE_TOKEN = server.obtain_OPAL_tokens()["datasource"]

        for location in locations:
            # Update policy to allow only non-US users
            print(f"Updating policy to allow only users from {location[1]}...")
            update_policy(gitea_server, server, location[1])

            for client in opal_clients:
                assert await data_publish_and_test(
                    "bob",
                    location[1],
                    locations,
                    DATASOURCE_TOKEN,
                    client,
                    server.settings.port,
                )


@pytest.mark.parametrize("attempts", [10])  # Number of attempts to repeat the check
def test_read_statistics(
    attempts,
    opal_servers: list[OpalServerContainer],
    number_of_opal_servers: int,
    number_of_opal_clients: int,
):
    """Tests the statistics feature by verifying the number of clients and
    servers."""

    print("- Testing statistics feature")

    time.sleep(15)

    for server in opal_servers:
        print(f"OPAL Server: {server.settings.container_name}:{server.settings.port}")

        # The URL for statistics
        stats_url = f"http://localhost:{server.settings.port}/stats"

        headers = {
            "Authorization": f"Bearer {server.obtain_OPAL_tokens()['datasource']}"
        }

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
                    pytest.fail(
                        f"Expected statistics not found in response: {response.text}"
                    )

                client_count = stats["client_count"]
                server_count = stats["server_count"]
                print(
                    f"Number of OPAL servers expected: {number_of_opal_servers}, found: {server_count}"
                )
                print(
                    f"Number of OPAL clients expected: {number_of_opal_clients}, found: {client_count}"
                )

                if server_count < number_of_opal_servers:
                    pytest.fail(
                        f"Expected number of servers not found in response: {response.text}"
                    )

                if client_count < number_of_opal_clients:
                    pytest.fail(
                        f"Expected number of clients not found in response: {response.text}"
                    )

            except requests.RequestException as e:
                if response is not None:
                    print(f"Request failed: {response.status_code} {response.text}")
                pytest.fail(f"Failed to fetch statistics: {e}")

    print("Statistics check passed in all attempts.")


@pytest.mark.asyncio
async def test_policy_update(
    gitea_server: GiteaContainer,
    opal_servers: list[OpalServerContainer],
    opal_clients: list[OpalClientContainer],
    temp_dir,
):
    # Parse locations into separate lists of IPs and countries
    location = "CN"

    # Generate the reference timestamp
    reference_timestamp = datetime.now(timezone.utc)
    logger.info(f"Reference timestamp: {reference_timestamp}")

    for server in opal_servers:
        # Update policy to allow only non-US users
        print(f"Updating policy to allow only users from {location}...")
        update_policy(gitea_server, server, "location")

        log_found = server.wait_for_log(
            "Found new commits: old HEAD was", 30, reference_timestamp
        )
        logger.info("Finished processing logs.")
        assert (
            log_found
        ), f"Expected log entry not found in server '{server.settings.container_name}' after the reference timestamp."

    for client in opal_clients:
        log_found = client.wait_for_log(
            "Fetching policy bundle from", 30, reference_timestamp
        )
        logger.info("Finished processing logs.")
        assert (
            log_found
        ), f"Expected log entry not found in client '{client.settings.container_name}' after the reference timestamp."


def test_with_statistics_disabled(opal_servers: list[OpalServerContainer]):
    assert True


def test_with_uvicorn_workers_and_no_broadcast_channel(
    opal_servers: list[OpalServerContainer],
):
    assert True


# TODO: Add more tests


def TD_test_two_servers_one_worker(opal_servers: list[OpalServerContainer]):
    assert True


def TD_test_switch_to_kafka_broadcast_channel(
    broadcast_channel: BroadcastContainerBase,
    opal_servers: list[OpalServerContainer],
    request,
):
    return True

    broadcast_channel.shutdown()

    kafka_broadcaster = request.getfixturevalue("kafka_broadcast_channel")

    kafka_broadcaster.start()

    for server in opal_servers:
        success = server.wait_for_log("broadcast channel is ready", 30)
        assert success, "Broadcast channel is not ready"

    assert False


def TD_test_switch_to_postgres_broadcast_channel(
    broadcast_channel: BroadcastContainerBase,
    opal_servers: list[OpalServerContainer],
    request,
):
    return True

    broadcast_channel.shutdown()

    postgres_broadcaster = request.getfixturevalue("postgres_broadcast_channel")

    postgres_broadcaster.start()

    for server in opal_servers:
        success = server.wait_for_log("broadcast channel is ready", 30)
        assert success, "Broadcast channel is not ready"

    assert False


def TD_test_switch__to_redis_broadcast_channel(
    broadcast_channel: BroadcastContainerBase,
    opal_servers: list[OpalServerContainer],
    request,
):
    return True

    broadcast_channel.shutdown()

    redis_broadcaster = request.getfixturevalue("redis_broadcast_channel")

    redis_broadcaster.start()

    for server in opal_servers:
        success = server.wait_for_log("broadcast channel is ready", 30)
        assert success, "Broadcast channel is not ready"

    assert False
