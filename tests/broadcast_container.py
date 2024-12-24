from testcontainers.postgres import PostgresContainer

from . import settings as s


class BroadcastContainer(PostgresContainer):
    def __init__(
        self,
        image: str = "postgres:alpine",
        docker_client_kw: dict | None = None,
        **kwargs,
    ) -> None:
        # Add custom labels to the kwargs
        labels = kwargs.get("labels", {})
        labels.update({"com.docker.compose.project": "pytest"})
        kwargs["labels"] = labels

        super().__init__(image=image, docker_client_kw=docker_client_kw, **kwargs)

        # Add a custom name for the container
        self.with_name(f"pytest_opal_broadcast_channel_{s.OPAL_TESTS_UNIQ_ID}")