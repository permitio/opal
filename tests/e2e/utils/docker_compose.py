"""
Docker Compose helper utilities for E2E tests.

Provides simple functions to interact with Docker Compose services.
"""

import subprocess
from pathlib import Path

try:
    import yaml
except ImportError:
    # Fallback: if yaml is not available, we'll use a simple parser
    yaml = None


def get_compose_file_path() -> Path:
    """
    Get the path to the E2E Docker Compose file.
    
    Returns:
        Path object pointing to docker-compose.e2e.yml
    """
    return Path(__file__).parent.parent.parent.parent / "docker" / "docker-compose.e2e.yml"


def run_compose_command(command: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """
    Run a docker compose command.
    
    Example:
        result = run_compose_command(["ps", "--format", "json"])
        print(result.stdout)
    
    Args:
        command: List of command arguments (e.g., ["up", "-d"])
        check: If True, raise exception on non-zero exit code
    
    Returns:
        CompletedProcess with stdout and stderr
    """
    compose_file = get_compose_file_path()
    full_command = ["docker", "compose", "-f", str(compose_file)] + command
    
    return subprocess.run(
        full_command,
        capture_output=True,
        text=True,
        check=check,
    )


def get_compose_services_from_yaml() -> list[str]:
    """
    Get list of service names by parsing the Docker Compose YAML file.
    
    This is the authoritative source of service names, independent of
    Docker runtime state. Parses docker-compose.e2e.yml directly.
    
    Example:
        services = get_compose_services_from_yaml()
        print(f"Found {len(services)} services: {services}")
    
    Returns:
        List of service names defined in docker-compose.e2e.yml
    """
    compose_file = get_compose_file_path()
    
    if not compose_file.exists():
        return []
    
    if yaml is None:
        # Fallback: simple line-based parsing if yaml library not available
        # This is less robust but works for basic cases
        services = []
        in_services_section = False
        with open(compose_file, "r") as f:
            for line in f:
                line = line.strip()
                if line == "services:":
                    in_services_section = True
                    continue
                if in_services_section:
                    # Service name is the first non-empty, non-comment line that ends with ':'
                    if line and not line.startswith("#") and line.endswith(":"):
                        service_name = line[:-1].strip()
                        if service_name and not service_name.startswith("_"):
                            services.append(service_name)
                    # Stop at top-level keys (not indented)
                    elif line and not line.startswith(" ") and not line.startswith("\t"):
                        break
        return services
    
    # Use YAML parser (preferred method)
    try:
        with open(compose_file, "r") as f:
            compose_data = yaml.safe_load(f)
        
        if not isinstance(compose_data, dict):
            return []
        
        services_section = compose_data.get("services", {})
        if not isinstance(services_section, dict):
            return []
        
        # Return list of service names (keys in services section)
        return list(services_section.keys())
    
    except Exception:
        # If YAML parsing fails, return empty list
        return []


def get_compose_services() -> list[str]:
    """
    Get list of service names from Docker Compose.
    
    Parses the docker-compose.e2e.yml file directly to extract service names.
    This is more reliable than using `docker compose ps --services` which
    can be unreliable in attached mode and CI environments.
    
    Example:
        services = get_compose_services()
        print(f"Found {len(services)} services: {services}")
    
    Returns:
        List of service names from docker-compose.e2e.yml
    """
    return get_compose_services_from_yaml()
