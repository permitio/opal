import os


class KafkaBroadcastSettings:
    def __init__(self, host, port, user, password, database):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database

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

        self.zookeeper_image_name = os.getenv(
            "ZOOKEEPER_IMAGE_NAME", "confluentinc/cp-zookeeper:6.2.0"
        )
        self.zookeeper_container_name = os.getenv(
            "ZOOKEEPER_CONTAINER_NAME", "zookeeper"
        )
        self.zookeeper_port = os.getenv("ZOOKEEPER_CLIENT_PORT", 2181)
        self.zookeeper_tick_time = os.getenv("ZOOKEEPER_TICK_TIME", 2000)
        self.zookeeper_allow_anonymous_login = os.getenv("ALLOW_ANONYMOUS_LOGIN", "yes")

        self.kafka_image_name = os.getenv(
            "KAFKA_IMAGE_NAME", "confluentinc/cp-kafka:6.2.0"
        )
        self.kafka_container_name = os.getenv("KAFKA_CONTAINER_NAME", "kafka")
        self.kafka_port = os.getenv("KAFKA_CLIENT_PORT", 9092)
        self.kafka_admin_port = os.getenv("KAFKA_ADMIN_PORT", 29092)

        self.kafka_ui_image_name = os.getenv(
            "KAFKA_UI_IMAGE_NAME", "provectuslabs/kafka-ui:latest"
        )
        self.kafka_ui_container_name = os.getenv("KAFKA_UI_CONTAINER_NAME", "kafka-ui")

        self.kafka_ui_port = os.getenv("KAFKA_UI_PORT", 8080)

        self.kafka_ui_url = os.getenv(
            "KAFKA_UI_URL", f"http://{self.kafka_ui_host}:{self.kafka_ui_port}"
        )

        self.broker_id = os.getenv("KAFKA_BROKER_ID", 1)
        self.zookeeper_connect = os.getenv(
            "KAFKA_ZOOKEEPER_CONNECT",
            f"{self.zookeeper_container_name}:{self.zookeeper_port}",
        )
        self.offsets_topic_replication_factor = os.getenv(
            "KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR", 1
        )
        self.listener_security_protocol_map = os.getenv(
            "KAFKA_LISTENER_SECURITY_PROTOCOL_MAP",
            "PLAINTEXT:PLAINTEXT,PLAINTEXT_HOST:PLAINTEXT",
        )
        self.advertised_listeners = os.getenv(
            "KAFKA_ADVERTISED_LISTENERS",
            f"PLAINTEXT_HOST://localhost:{self.kafka_admin_port},PLAINTEXT://{self.kafka_container_name}:{self.kafka_port}",
        )
        self.allow_plaintext_listener = os.getenv("ALLOW_PLAINTEXT_LISTENER", "yes")
        self.kafka_topic_auto_create = os.getenv("KAFKA_TOPIC_AUTO_CREATE", "true")
        self.kafka_transaction_state_log_min_isr = os.getenv(
            "KAFKA_TRANSACTION_STATE_LOG_MIN_ISR", 1
        )
        self.kafka_transaction_state_log_replication_factor = os.getenv(
            "KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR", 1
        )
        self.kafka_clusters_bootstrapservers = os.getenv(
            "KAFKA_CLUSTERS_0_BOOTSTRAPSERVERS",
            f"{self.kafka_container_name}:{self.kafka_port}",
        )
