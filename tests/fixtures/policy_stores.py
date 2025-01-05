import pytest
from testcontainers.core.network import Network

from tests.containers.cedar_container import CedarContainer
from tests.containers.opa_container import OpaContainer, OpaSettings
from tests.containers.settings.cedar_settings import CedarSettings


@pytest.fixture(scope="session")
def opa_server(opal_network: Network, opa_image):
    with OpaContainer(
        settings=OpaSettings(
            container_name="opa",
            image=opa_image,
        ),
        network=opal_network,
    ) as container:
        assert container.wait_for_log(
            log_str="Server started", timeout=30
        ), "OPA server did not start."
        yield container

        container.stop()


@pytest.fixture(scope="session")
def cedar_server(opal_network: Network, cedar_image):
    with CedarContainer(
        settings=CedarSettings(
            container_name="cedar",
            image=cedar_image,
        ),
        network=opal_network,
    ) as container:
        assert container.wait_for_log(
            log_str="Server started", timeout=30
        ), "CEDAR server did not start."
        yield container

        container.stop()
