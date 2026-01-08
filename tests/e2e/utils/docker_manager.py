import docker
import subprocess
import time
from pathlib import Path
from typing import Optional, List


class DockerManager:
    """Manages Docker Compose lifecycle for E2E tests."""

    def __init__(self, compose_file: Path, project_name: str):
        """
        Initialize Docker manager.

        Args:
            compose_file: Path to docker-compose.yml file
            project_name: Docker Compose project name
        """
        self.compose_file = compose_file
        self.project_name = project_name
        try:
            self.client = docker.from_env()
        except docker.errors.DockerException as e:
            raise RuntimeError(f"Failed to connect to Docker daemon: {e}")

    def up(self, detach: bool = True, build: bool = False) -> subprocess.CompletedProcess:
        """
        Start Docker Compose services.

        Args:
            detach: Run services in background
            build: Build images before starting

        Returns:
            Completed process result

        Raises:
            RuntimeError: If services fail to start
        """
        try:
            cmd = [
                "docker", "compose",
                "-f", str(self.compose_file),
                "-p", self.project_name,
                "up"
            ]

            if detach:
                cmd.append("-d")
            if build:
                cmd.append("--build")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )
            return result

        except subprocess.CalledProcessError as e:
            error_msg = f"Failed to start services: {e.stderr}"
            print(error_msg)
            self.down(remove_volumes=True)
            raise RuntimeError(error_msg)

    def down(self, remove_volumes: bool = False, remove_images: bool = False) -> bool:
        """
        Stop and remove Docker Compose services.

        Args:
            remove_volumes: Remove volumes
            remove_images: Remove images

        Returns:
            True if successful, False otherwise
        """
        try:
            cmd = [
                "docker", "compose",
                "-f", str(self.compose_file),
                "-p", self.project_name,
                "down"
            ]

            if remove_volumes:
                cmd.append("-v")
            if remove_images:
                cmd.extend(["--rmi", "all"])

            subprocess.run(cmd, capture_output=True, check=False)
            return True

        except Exception as e:
            print(f"Warning: Error during cleanup: {e}")
            return False

    def wait_for_healthy(self, service_name: str, timeout: int = 60) -> bool:
        """
        Wait for a service to become healthy.

        Args:
            service_name: Name of the service
            timeout: Maximum time to wait in seconds

        Returns:
            True if service is healthy

        Raises:
            TimeoutError: If service doesn't become healthy within timeout
            RuntimeError: If service becomes unhealthy
        """
        start = time.time()

        while time.time() - start < timeout:
            try:
                container = self.get_container(service_name)

                if not container:
                    time.sleep(2)
                    continue

                health = container.attrs.get('State', {}).get('Health', {})
                status = health.get('Status', 'none')

                if status == 'healthy':
                    return True
                elif status == 'unhealthy':
                    logs = container.logs(tail=50).decode()
                    raise RuntimeError(
                        f"Service {service_name} is unhealthy. Last 50 log lines:\n{logs}"
                    )

                container_state = container.attrs.get('State', {})
                if container_state.get('Status') == 'running' and status == 'none':
                    return True

                time.sleep(2)

            except docker.errors.NotFound:
                time.sleep(2)
                continue

        try:
            container = self.get_container(service_name)
            if container:
                logs = container.logs(tail=100).decode()
                raise TimeoutError(
                    f"Service {service_name} did not become healthy within {timeout}s. "
                    f"Last 100 log lines:\n{logs}"
                )
        except docker.errors.NotFound:
            pass

        raise TimeoutError(f"Service {service_name} not found after {timeout}s")

    def get_container(self, service_name: str) -> Optional[docker.models.containers.Container]:
        """
        Get container for a service.

        Args:
            service_name: Name of the service

        Returns:
            Container object or None if not found
        """
        try:
            containers = self.client.containers.list(
                filters={
                    "label": [
                        f"com.docker.compose.project={self.project_name}",
                        f"com.docker.compose.service={service_name}"
                    ]
                }
            )

            if containers:
                return containers[0]

            return None

        except docker.errors.DockerException as e:
            print(f"Error getting container for {service_name}: {e}")
            return None

    def get_logs(self, service_name: str, tail: Optional[int] = None) -> str:
        """
        Get logs from a service.

        Args:
            service_name: Name of the service
            tail: Number of lines to retrieve from end (None for all)

        Returns:
            Container logs as string

        Raises:
            RuntimeError: If container not found
        """
        container = self.get_container(service_name)

        if not container:
            raise RuntimeError(f"Container for service {service_name} not found")

        kwargs = {}
        if tail is not None:
            kwargs['tail'] = tail

        return container.logs(**kwargs).decode('utf-8', errors='replace')

    def list_services(self) -> List[str]:
        """
        List all services in the compose project.

        Returns:
            List of service names
        """
        containers = self.client.containers.list(
            filters={"label": f"com.docker.compose.project={self.project_name}"}
        )

        service_names = set()
        for container in containers:
            labels = container.labels
            service_name = labels.get('com.docker.compose.service')
            if service_name:
                service_names.add(service_name)

        return list(service_names)

    def is_service_running(self, service_name: str) -> bool:
        """
        Check if a service is running.

        Args:
            service_name: Name of the service

        Returns:
            True if service is running
        """
        container = self.get_container(service_name)
        if not container:
            return False

        return container.status == 'running'

    def restart_service(self, service_name: str, timeout: int = 10) -> bool:
        """
        Restart a service.

        Args:
            service_name: Name of the service
            timeout: Timeout for restart operation

        Returns:
            True if successful
        """
        container = self.get_container(service_name)
        if not container:
            return False

        try:
            container.restart(timeout=timeout)
            return True
        except docker.errors.DockerException as e:
            print(f"Error restarting {service_name}: {e}")
            return False
