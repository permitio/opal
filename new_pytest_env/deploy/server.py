# from testcontainers.core.network import Network
# from testcontainers.core.generic import DockerContainer
# from testcontainers.core.utils import setup_logger
# import requests


# class OPALServer:
#     def __init__(
#         self,
#         image: str,
#         container_name: str,
#         network_name: str,
#         port: int,
#         uvicorn_workers: str,
#         policy_repo_url: str,
#         polling_interval: str,
#         private_key: str,
#         public_key: str,
#         master_token: str,
#         data_topics: str,
#         broadcast_uri: str = None,
#     ):
#         """
#         Initialize the OPAL Server with the provided parameters.

#         :param image: Docker image for the OPAL server.
#         :param container_name: Name of the Docker container.
#         :param network_name: Name of the Docker network to attach.
#         :param port: Exposed port for the OPAL server.
#         :param uvicorn_workers: Number of Uvicorn workers.
#         :param policy_repo_url: URL of the policy repository.
#         :param polling_interval: Polling interval for the policy repository.
#         :param private_key: SSH private key for authentication.
#         :param public_key: SSH public key for authentication.
#         :param master_token: Master token for OPAL authentication.
#         :param data_topics: Data topics for OPAL configuration.
#         :param broadcast_uri: Optional URI for the broadcast channel.
#         """
#         self.image = image
#         self.container_name = container_name
#         self.network_name = network_name
#         self.port = port
#         self.uvicorn_workers = uvicorn_workers
#         self.policy_repo_url = policy_repo_url
#         self.polling_interval = polling_interval
#         self.private_key = private_key
#         self.public_key = public_key
#         self.master_token = master_token
#         self.data_topics = data_topics
#         self.broadcast_uri = broadcast_uri

#         self.container = None
#         self.log = setup_logger(__name__)

#     def validate_dependencies(self):
#         """Validate required dependencies before starting the server."""
#         if not self.policy_repo_url:
#             raise ValueError("OPAL_POLICY_REPO_URL is required.")
#         if not self.private_key or not self.public_key:
#             raise ValueError("SSH private and public keys are required.")
#         if not self.master_token:
#             raise ValueError("OPAL master token is required.")
#         self.log.info("Dependencies validated successfully.")

#     def start_server(self, net: Network):
#         """Start the OPAL Server Docker container."""
#         self.validate_dependencies()

#         # Configure environment variables
#         env_vars = {
#             "UVICORN_NUM_WORKERS": self.uvicorn_workers,
#             "OPAL_POLICY_REPO_URL": self.policy_repo_url,
#             "OPAL_POLICY_REPO_POLLING_INTERVAL": self.polling_interval,
#             "OPAL_AUTH_PRIVATE_KEY": self.private_key,
#             "OPAL_AUTH_PUBLIC_KEY": self.public_key,
#             "OPAL_AUTH_MASTER_TOKEN": self.master_token,
#             "OPAL_DATA_CONFIG_SOURCES": f"""{{"config":{{"entries":[{{"url":"http://localhost:{self.port}/policy-data","topics":["{self.data_topics}"],"dst_path":"/static"}}]}}}}""",
#             "OPAL_LOG_FORMAT_INCLUDE_PID": "true",
#             "OPAL_STATISTICS_ENABLED": "true",
#         }

#         if self.broadcast_uri:
#             env_vars["OPAL_BROADCAST_URI"] = self.broadcast_uri

#         # Create the DockerContainer object
#         self.log.info(f"Starting OPAL Server container: {self.container_name}")
#         self.container = DockerContainer(self.image)

#         # Add environment variables individually
#         for key, value in env_vars.items():
#             self.container = self.container.with_env(key, value)

#         # Configure network and other settings
#         self.container \
#             .with_name(self.container_name) \
#             .with_bind_ports(7002, self.port) \
#             .with_network(net) \
#             .with_network_aliases("server") \

#         # Start the container
#         self.container.start()
#         #self.log.info(f"OPAL Server container started with ID: {self.container.container_id}")

#     def stop_server(self):
#         """Stop and remove the OPAL Server Docker container."""
#         if self.container:
#             self.log.info(f"Stopping OPAL Server container: {self.container_name}")
#             self.container.stop()
#             self.container = None
#             self.log.info("OPAL Server container stopped and removed.")

#     def obtain_OPAL_tokens(self):
#         """Fetch client and datasource tokens from the OPAL server."""
#         token_url = f"http://localhost:{self.port}/token"
#         headers = {
#             "Authorization": f"Bearer {self.master_token}",
#             "Content-Type": "application/json",
#         }

#         tokens = {}

#         for token_type in ["client", "datasource"]:
#             try:
#                 data = {"type": token_type}#).replace("'", "\"")
#                 self.log.info(f"Fetching OPAL {token_type} token...")
#                 self.log.info(f"url: {token_url}")
#                 self.log.info(f"headers: {headers}")
#                 self.log.info(data)

#                 response = requests.post(token_url, headers=headers, json=data)
#                 response.raise_for_status()

#                 token = response.json().get("token")
#                 if token:
#                     tokens[token_type] = token
#                     self.log.info(f"Successfully fetched OPAL {token_type} token.")
#                 else:
#                     self.log.error(f"Failed to fetch OPAL {token_type} token: {response.json()}")

#             except requests.exceptions.RequestException as e:
#                 self.log.error(f"HTTP Request failed while fetching OPAL {token_type} token: {e}")

#         return tokens
