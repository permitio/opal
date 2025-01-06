from tests import utils


class CedarSettings:
    def __init__(
        self,
        image: str | None = None,
        port: int | None = None,
        container_name: str | None = None,
    ) -> None:
        self.image = image if image else "permitio/cedar:latest"
        self.container_name = container_name if container_name else "cedar"

        if port is None:
            self.port = utils.find_available_port(8180)
        else:
            if utils.is_port_available(port):
                self.port = port
            else:
                self.port = utils.find_available_port(8180)

    def getEnvVars(self):
        return {}
