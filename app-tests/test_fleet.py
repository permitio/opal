"""E2E checks of a fleet of two OPAL servers and two OPAL clients.

The tests share one stack and run in file order: the broadcaster outages
come last, after the checks that need a fleet that has not been through one.
Each test waits for the state it needs, so any one of them also runs alone.
"""

import pytest
from stack import (
    BACKBONE_CONNECTED,
    BACKBONE_DROPPED,
    BACKBONE_RESYNC,
    REPLICAS,
    SERVER_GOT_UPDATE_REPORT,
    Fleet,
    PolicyRepo,
    wait_until,
)

FROZEN = "freezing publish to preserve fleet consistency"
BUFFERED = "buffered for replay"
REPLAYED = "Replaying"
FREEZE_SUMMARY = "publish(es) during the gap"
DISCONNECT_ERROR = "list.remove(x): x not in list"

# How many CA certificates the default SSL context loads, the context a client's HTTPS
# fetches use. It reads the image's trust store and needs no network.
CA_CERTIFICATES = (
    "import ssl; print(ssl.create_default_context().cert_store_stats()['x509_ca'])"
)


def data_applied(user: str) -> str:
    return f"PUT /v1/data/users/{user}/location -> 204"


def publish_and_expect(fleet: Fleet, user: str) -> None:
    fleet.publish_data(user)
    fleet.wait_for_each_client(data_applied(user))


def push_and_expect(fleet: Fleet, policy_repo: PolicyRepo, package: str) -> None:
    name = policy_repo.push_policy(package)
    fleet.notify_push(policy_repo.server_url)
    fleet.wait_for_each_client(f"PUT /v1/policies/{name} -> 200")


@pytest.mark.policy_repo
def test_no_client_logs_an_error_at_startup(fleet: Fleet) -> None:
    # Each client reports its first data update to a server from a task that runs after
    # the update is saved. Once both reports are in, the clients get the 15 s that
    # run.sh gave them after compose up to log an error.
    fleet.wait_for_servers(SERVER_GOT_UPDATE_REPORT, since=len(REPLICAS) - 1)
    fleet.assert_not_logged_for("opal_client", "ERROR", seconds=15)


def test_each_client_trusts_a_full_ca_bundle(fleet: Fleet) -> None:
    for replica in REPLICAS:
        loaded = fleet.compose(
            "exec",
            "-T",
            "--index",
            str(replica),
            "opal_client",
            "python",
            "-c",
            CA_CERTIFICATES,
        )
        # A full public bundle holds over 100 roots; an empty or unreadable one, none.
        assert int(loaded) >= 100, f"client {replica} loads {loaded.strip()} CAs"


def test_a_data_update_reaches_every_client(fleet: Fleet) -> None:
    publish_and_expect(fleet, "bob")


@pytest.mark.policy_repo
def test_a_pushed_policy_reaches_every_client(
    fleet: Fleet, policy_repo: PolicyRepo
) -> None:
    push_and_expect(fleet, policy_repo, "something")


def test_every_server_counts_two_servers_and_two_clients(fleet: Fleet) -> None:
    for replica in REPLICAS:
        reads: list[dict] = []

        def eight_reads_agree() -> bool:
            # Each read may land on a different worker of the server.
            reads[:] = [fleet.statistics(replica) for _ in range(8)]
            return all(
                read["client_count"] == 2 and read["server_count"] == 2
                for read in reads
            )

        assert wait_until(eight_reads_agree, timeout=60), (replica, reads)


def test_updates_reach_every_client_after_a_broadcaster_restart(
    fleet: Fleet, policy_repo: PolicyRepo
) -> None:
    resyncs = fleet.worker_counts(BACKBONE_RESYNC)

    fleet.compose("restart", "broadcast_channel")
    fleet.wait_for_broadcaster()
    fleet.wait_for_resync(resyncs)

    publish_and_expect(fleet, "alice")
    push_and_expect(fleet, policy_repo, "another")


def test_updates_reach_every_client_after_the_broadcaster_is_killed(
    fleet: Fleet, policy_repo: PolicyRepo
) -> None:
    drops = fleet.worker_counts(*BACKBONE_DROPPED)
    connects = fleet.worker_counts(BACKBONE_CONNECTED)
    resyncs = fleet.worker_counts(BACKBONE_RESYNC)

    fleet.compose("kill", "broadcast_channel")
    fleet.wait_for_every_listener(BACKBONE_DROPPED, drops, timeout=30)
    fleet.compose("up", "--detach", "broadcast_channel")
    fleet.wait_for_broadcaster()
    fleet.wait_for_resync(resyncs)

    publish_and_expect(fleet, "sunil")
    publish_and_expect(fleet, "eve")
    push_and_expect(fleet, policy_repo, "best_one_yet")
    # Every worker reconnected to the broadcast channel, and none raised the error
    # a second disconnect of the same client used to raise.
    fleet.wait_for_every_listener((BACKBONE_CONNECTED,), connects, timeout=10)
    fleet.assert_not_logged("opal_server", DISCONNECT_ERROR)


def test_the_fleet_stays_consistent_across_a_backbone_outage(fleet: Fleet) -> None:
    """A data update published while the broadcast channel is down reaches no
    client, so the clients of one server never see what the other server's
    clients do not.

    One-off updates are not part of the clients' data sources, so the
    frozen update is dropped; publishing it again after the recovery
    reaches every client.
    """
    user = "consistency_user"
    drops = fleet.worker_counts(*BACKBONE_DROPPED)
    resyncs = fleet.worker_counts(BACKBONE_RESYNC)
    before = {
        text: fleet.server_lines(text)
        for text in (FROZEN, BUFFERED, REPLAYED, FREEZE_SUMMARY)
    }

    fleet.compose("kill", "broadcast_channel")
    fleet.wait_for_every_listener(BACKBONE_DROPPED, drops, timeout=30)
    fleet.publish_data(user)
    fleet.wait_for_servers(FROZEN, since=before[FROZEN])
    # Internal topics are not frozen: the servers buffer them for a replay.
    fleet.wait_for_servers(BUFFERED, since=before[BUFFERED], timeout=60)

    fleet.compose("up", "--detach", "broadcast_channel")
    fleet.wait_for_broadcaster()
    fleet.wait_for_resync(resyncs)
    fleet.wait_for_servers(REPLAYED, since=before[REPLAYED])
    # Neither during the gap nor through the replay.
    fleet.assert_not_logged("opal_client", data_applied(user))

    publish_and_expect(fleet, user)
    # The server that froze the update says so on its next delivered publish.
    fleet.wait_for_servers(FREEZE_SUMMARY, since=before[FREEZE_SUMMARY])
