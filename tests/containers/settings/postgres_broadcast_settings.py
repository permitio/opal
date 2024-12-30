
import os

class PostgresBroadcastSettings:
    def __init__(
        self, 
        host, 
        port, 
        user, 
        password, 
        database):
        
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
            "POSTGRES_DATABASE": self.database
        }
    
    def load_from_env(self):
        self.host = os.getenv("POSTGRES_HOST", "localhost")
        self.port = int(os.getenv("POSTGRES_PORT", 5432))
        self.user = os.getenv("POSTGRES_USER", "postgres")
        self.password = os.getenv("POSTGRES_PASSWORD", "postgres")
        self.database = os.getenv("POSTGRES_DATABASE", "postgres")