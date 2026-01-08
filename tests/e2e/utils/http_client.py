import requests
from typing import Dict, Any, Optional
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class OpalHttpClient:
    """HTTP client for OPAL API with automatic retry logic."""

    def __init__(self, base_url: str, timeout: int = 10):
        """
        Initialize HTTP client.

        Args:
            base_url: Base URL for the OPAL service (e.g., http://localhost:17002)
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        """Create session with retry strategy."""
        session = requests.Session()

        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["GET", "POST", "PUT", "DELETE", "HEAD"]
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        return session

    def get(self, endpoint: str, **kwargs) -> requests.Response:
        """
        Make GET request.

        Args:
            endpoint: API endpoint (e.g., /healthcheck)
            **kwargs: Additional arguments passed to requests.get

        Returns:
            Response object
        """
        url = f"{self.base_url}{endpoint}"
        return self.session.get(url, timeout=self.timeout, **kwargs)

    def post(self, endpoint: str, **kwargs) -> requests.Response:
        """
        Make POST request.

        Args:
            endpoint: API endpoint
            **kwargs: Additional arguments passed to requests.post

        Returns:
            Response object
        """
        url = f"{self.base_url}{endpoint}"
        return self.session.post(url, timeout=self.timeout, **kwargs)

    def put(self, endpoint: str, **kwargs) -> requests.Response:
        """
        Make PUT request.

        Args:
            endpoint: API endpoint
            **kwargs: Additional arguments passed to requests.put

        Returns:
            Response object
        """
        url = f"{self.base_url}{endpoint}"
        return self.session.put(url, timeout=self.timeout, **kwargs)

    def delete(self, endpoint: str, **kwargs) -> requests.Response:
        """
        Make DELETE request.

        Args:
            endpoint: API endpoint
            **kwargs: Additional arguments passed to requests.delete

        Returns:
            Response object
        """
        url = f"{self.base_url}{endpoint}"
        return self.session.delete(url, timeout=self.timeout, **kwargs)

    def get_json(self, endpoint: str, **kwargs) -> Dict[str, Any]:
        """
        Make GET request and return JSON response.

        Args:
            endpoint: API endpoint
            **kwargs: Additional arguments passed to requests.get

        Returns:
            Parsed JSON response

        Raises:
            HTTPError: If response status is not successful
            JSONDecodeError: If response is not valid JSON
        """
        response = self.get(endpoint, **kwargs)
        response.raise_for_status()
        return response.json()

    def close(self):
        """Close the HTTP session."""
        self.session.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
