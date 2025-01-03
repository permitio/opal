import os


class PostgresBroadcastSettings:
    def __init__(
        self,
        container_name: str | None = None,
        host: str | None = None,
        port: int | None = None,
        user: str | None = None,
        password: str | None = None,
        database: str | None = None,
    ):
        self.load_from_env()

        self.container_name = container_name if container_name else self.container_name
        self.host = host if host else self.host
        self.port = port if port else self.port
        self.user = user if user else self.user
        self.password = password if password else self.password
        self.database = database if database else self.database
        self.protocol = "postgres"

        self.validate_dependencies()

    def validate_dependencies(self):
        """Validate required dependencies before starting the server."""
        if not self.host:
            raise ValueError("POSTGRES_HOST is required.")
        if not self.port:
            raise ValueError("POSTGRES_PORT is required.")
        if not self.user:
            raise ValueError("POSTGRES_USER is required.")
        if not self.password:
            raise ValueError("POSTGRES_PASSWORD is required.")
        if not self.database:
            raise ValueError("POSTGRES_DATABASE is required.")

    def getEnvVars(self):
        return {
            "POSTGRES_HOST": self.host,
            "POSTGRES_PORT": self.port,
            "POSTGRES_USER": self.user,
            "POSTGRES_PASSWORD": self.password,
            "POSTGRES_DATABASE": self.database,
        }

    def load_from_env(self):
        self.host = os.getenv("POSTGRES_HOST", "localhost")
        self.port = int(os.getenv("POSTGRES_PORT", 5432))
        self.user = os.getenv("POSTGRES_USER", "postgres")
        self.password = os.getenv("POSTGRES_PASSWORD", "postgres")
        self.database = os.getenv("POSTGRES_DATABASE", "postgres")
        self.container_name = os.getenv("POSTGRES_CONTAINER_NAME", "broadcast_channel")
