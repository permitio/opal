from pydantic import BaseSettings, Field
from typing import Optional
from pathlib import Path
import os

class OPALEnvironment(BaseSettings):
    """Environment configuration for OPAL tests with support for .env file"""
    # Server Configuration
    SERVER_PORT: int = Field(7002, description="OPAL server port")
    SERVER_HOST: str = Field("0.0.0.0", description="OPAL server host")
    SERVER_WORKERS: int = Field(4, description="Number of server workers")
    SERVER_LOG_LEVEL: str = Field("DEBUG", description="Server log level")
    SERVER_MASTER_TOKEN: str = Field("master-token-for-testing", description="Server master token")

    # Client Configuration
    CLIENT_PORT: int = Field(7000, description="OPAL client port")
    CLIENT_HOST: str = Field("0.0.0.0", description="OPAL client host")
    CLIENT_TOKEN: str = Field("default-token-for-testing", description="Client auth token")
    CLIENT_LOG_LEVEL: str = Field("DEBUG", description="Client log level")

    # Database Configuration
    POSTGRES_PORT: int = Field(5432, description="PostgreSQL port")
    POSTGRES_HOST: str = Field("broadcast_channel", description="PostgreSQL host")
    POSTGRES_DB: str = Field("postgres", description="PostgreSQL database")
    POSTGRES_USER: str = Field("postgres", description="PostgreSQL user")
    POSTGRES_PASSWORD: str = Field("postgres", description="PostgreSQL password")


    # Statistics Configuration
    STATISTICS_ENABLED: bool = Field(True, description="Enable statistics collection")
    STATISTICS_CHECK_TIMEOUT: int = Field(10, description="Timeout for statistics checks in seconds")

    # Policy Configuration
    POLICY_REPO_URL: str = Field(
        "https://github.com/permitio/opal-example-policy-repo",
        description="Git repository URL for policies"
    )
    POLICY_REPO_POLLING_INTERVAL: int = Field(30, description="Policy repo polling interval in seconds")

    # Network Configuration
    NETWORK_NAME: str = Field("opal_test_network", description="Docker network name")

    # Authentication Configuration
    AUTH_JWT_AUDIENCE: str = Field("https://api.opal.ac/v1/", description="JWT audience")
    AUTH_JWT_ISSUER: str = Field("https://opal.ac/", description="JWT issuer")

    # Test Configuration
    TEST_TIMEOUT: int = Field(300, description="Test timeout in seconds")
    TEST_RETRY_INTERVAL: int = Field(2, description="Retry interval in seconds")
    TEST_MAX_RETRIES: int = Field(30, description="Maximum number of retries")

    class Config:
        env_file = '.env'
        env_file_encoding = 'utf-8'
        case_sensitive = True

    @property
    def postgres_dsn(self) -> str:
        """Get PostgreSQL connection string"""
        return f"postgres://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @classmethod
    def load_from_env_file(cls, env_file: str = '.env') -> 'OPALEnvironment':
        """Load configuration from specific env file"""
        if not os.path.exists(env_file):
            raise FileNotFoundError(f"Environment file not found: {env_file}")

        return cls(_env_file=env_file)

def get_environment() -> OPALEnvironment:
    """Get environment configuration, with support for local development overrides"""
    # Try local dev config first
    local_env = Path('.env.local')
    if local_env.exists():
        return OPALEnvironment.load_from_env_file('.env.local')

    # Fallback to default .env
    default_env = Path('.env')
    if default_env.exists():
        return OPALEnvironment.load_from_env_file('.env')

    # Use defaults/environment variables
    return OPALEnvironment()