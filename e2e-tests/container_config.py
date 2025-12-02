"""Container configuration helpers"""
import json
from testcontainers.core.container import DockerContainer
from config import OPALEnvironment

def configure_postgres(container: DockerContainer, config: OPALEnvironment):
    """Configure Postgres container"""
    container.with_env("POSTGRES_DB", config.POSTGRES_DB)
    container.with_env("POSTGRES_USER", config.POSTGRES_USER)
    container.with_env("POSTGRES_PASSWORD", config.POSTGRES_PASSWORD)
    container.with_exposed_ports(config.POSTGRES_PORT)
    container.with_kwargs(network=config.NETWORK_NAME)

def configure_server(container: DockerContainer, config: OPALEnvironment):
    """Configure OPAL server container with all required environment variables"""
    env_vars = {
        "PORT": str(config.SERVER_PORT),
        "HOST": config.SERVER_HOST,
        "UVICORN_NUM_WORKERS": str(config.SERVER_WORKERS),
        "LOG_LEVEL": config.SERVER_LOG_LEVEL,
        "OPAL_STATISTICS_ENABLED": "true",
        "OPAL_BROADCAST_URI": config.postgres_dsn,
        "BROADCAST_CHANNEL_NAME": "opal_updates",
        "OPAL_POLICY_REPO_URL": config.POLICY_REPO_URL,
        "OPAL_POLICY_REPO_POLLING_INTERVAL": str(config.POLICY_REPO_POLLING_INTERVAL),
        "OPAL_DATA_CONFIG_SOURCES": json.dumps({
            "config": {
                "entries": [{
                    "url": "http://opal_server:7002/policy-data",
                    "topics": ["policy_data"],
                    "dst_path": "/static"
                }]
            }
        }),
        "AUTH_JWT_AUDIENCE": config.AUTH_JWT_AUDIENCE,
        "AUTH_JWT_ISSUER": config.AUTH_JWT_ISSUER,
        "AUTH_MASTER_TOKEN": config.SERVER_MASTER_TOKEN,
        "OPAL_LOG_FORMAT_INCLUDE_PID": "true",
        "LOG_FORMAT": "text",
        "LOG_TRACEBACK": "true"
    }

    for key, value in env_vars.items():
        container.with_env(key, value)

    container.with_exposed_ports(config.SERVER_PORT)
    container.with_kwargs(network=config.NETWORK_NAME)

def configure_client(container: DockerContainer, config: OPALEnvironment):
    """Configure OPAL client container with all required environment variables"""
    env_vars = {
        "OPAL_SERVER_URL": f"http://opal_server:{config.SERVER_PORT}",
        "PORT": str(config.CLIENT_PORT),
        "HOST": config.CLIENT_HOST,
        "LOG_LEVEL": config.CLIENT_LOG_LEVEL,
        "OPAL_CLIENT_TOKEN": config.CLIENT_TOKEN,
        "AUTH_JWT_AUDIENCE": config.AUTH_JWT_AUDIENCE,
        "AUTH_JWT_ISSUER": config.AUTH_JWT_ISSUER,
        "POLICY_UPDATER_ENABLED": "true",
        "DATA_UPDATER_ENABLED": "true",
        "INLINE_OPA_ENABLED": "true",
        "OPA_HEALTH_CHECK_POLICY_ENABLED": "true",
        "OPAL_INLINE_OPA_LOG_FORMAT": "http",
        "INLINE_OPA_CONFIG": "{}",
        "OPAL_STATISTICS_ENABLED": "true",
        "OPAL_LOG_FORMAT_INCLUDE_PID": "true",
        "LOG_FORMAT": "text",
        "LOG_TRACEBACK": "true"
    }

    for key, value in env_vars.items():
        container.with_env(key, value)

    container.with_exposed_ports(config.CLIENT_PORT, 8181)
    container.with_kwargs(network=config.NETWORK_NAME)