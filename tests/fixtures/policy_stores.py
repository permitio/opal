import pytest
from testcontainers.core.network import Network

from tests.containers.cedar_container import CedarContainer
from tests.containers.opa_container import OpaContainer, OpaSettings
from tests.containers.settings.cedar_settings import CedarSettings
from tests.fixtures.images import cedar_image, opa_image


@pytest.fixture(scope="session")
def opa_server(opal_network: Network, opa_image):
    """OPA server fixture.

    This fixture starts an OPA server and stops it after all tests have been
    executed. The OPA server is started in a separate thread and is available
    under the name "opa" in the test container network.

    The fixture yields the container object, which can be used to access the
    container logs or to execute commands inside the container.

    The fixture is scoped to the session, meaning it is executed only once per
    test session.

    Parameters
    ----------
    opal_network : Network
        The network to which the OPA server should be connected.
    opa_image : str
        The OPA server image to use.

    Yields
    ------
    container : OpaContainer
        The OPA server container object.
    """
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
    """CEDAR server fixture.

    This fixture starts a CEDAR server and stops it after all tests have been
    executed. The CEDAR server is started in a separate thread and is available
    under the name "cedar" in the test container network.

    The fixture yields the container object, which can be used to access the
    container logs or to execute commands inside the container.

    The fixture is scoped to the session, meaning it is executed only once per
    test session.

    Parameters
    ----------
    opal_network : Network
        The network to which the CEDAR server should be connected.
    cedar_image : str
        The CEDAR server image to use.

    Yields
    ------
    container : CedarContainer
        The CEDAR server container object.
    """
    with CedarContainer(
        settings=CedarSettings(
            container_name="cedar",
            image=cedar_image,
        ),
        network=opal_network,
    ) as container:
        # assert container.wait_for_log(
        #     log_str="Server started", timeout=30
        # ), "CEDAR server did not start."
        yield container

        container.stop()
