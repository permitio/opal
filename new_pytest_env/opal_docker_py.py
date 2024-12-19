import docker
import time
import os
import subprocess
import requests
from dotenv import load_dotenv

# Load .env file if it exists
load_dotenv()


OPAL_server_image = "permitio/opal-server:latest"
OPAL_client_image = "permitio/opal-client:latest"



temp_dir = None
command = None
filename = "OPAL_test_ssh_key"
network_name = None
OPAL_server_uvicorn_num_workers = None
OPAL_POLICY_REPO_URL = None
OPAL_POLICY_REPO_POLLING_INTERVAL = None
OPAL_server_container_name = None
OPAL_client_container_name = None
OPAL_server_7002_port = None
OPAL_client_7000_port = None
OPAL_client_8181_port = None
OPAL_DATA_TOPICS = None
OPAL_SERVER_URL = None

# Initialize Docker client
client = docker.DockerClient(base_url="unix://var/run/docker.sock")


OPAL_client_token = None
OPAL_datasource_token = None
OPAL_master_token = None
private_key = None
public_key = None


server_container = None
client_container = None


def prepare_SSH_keys():
    
    global temp_dir, filename

    try:
        # Generate the SSH key pair
        subprocess.run(command, check=True)
        print(f"SSH key pair generated successfully! Files: {filename}, {filename}.pub")
        
        # Load the private and public keys into variables
        with open(os.path.join(temp_dir, filename), "r") as private_key_file:
            private = private_key_file.read()

        with open(os.path.join(temp_dir, f"{filename}.pub"), "r") as public_key_file:
            public = public_key_file.read()

        print("Private Key Loaded:")
        print(private)
        print("\nPublic Key Loaded:")
        print(public)
        return public, private
    
    except subprocess.CalledProcessError as e:
        print(f"Error occurred: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")


def prepare_OPAL_master_key():

    global OPAL_master_token

    try:    
        # Run 'opal-server generate-secret' and save the output
        OPAL_master_token = subprocess.check_output(["opal-server", "generate-secret"], text=True).strip()
        print(f"OPAL_AUTH_MASTER_TOKEN: {OPAL_master_token}")
        
    except subprocess.CalledProcessError as e:
        print(f"Error occurred: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")


def prepare_keys():

    global OPAL_master_token, public_key, private_key, temp_dir

    public_key, private_key = prepare_SSH_keys()
    prepare_OPAL_master_key()


    # Persist the updated value for future runs
    with open(os.path.join(temp_dir, "OPAL_master_token.tkn"), "w") as env_file:
        env_file.write(OPAL_master_token)

def prepare_network():

    global network_name, client

    if network_name not in [network.name for network in client.networks.list()]:
        print(f"Creating network: {network_name}")
        client.networks.create(network_name, driver="bridge")

def pull_OPAL_images():

    global OPAL_client_image, OPAL_server_image, client

    try:
        # Pull the required images
        print("Pulling OPAL Server image...")
        client.images.pull(OPAL_server_image)

        print("Pulling OPAL Client image...")
        client.images.pull(OPAL_client_image)

    except requests.exceptions.RequestException as e:
        print(f"HTTP Request failed: {e}")
    except docker.errors.APIError as e:
        print(f"Error with Docker API: {e}")
    except docker.errors.ImageNotFound as e:
        print(f"Error pulling images: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")

def prepare_OPAL_server():
    
    global OPAL_server_uvicorn_num_workers, OPAL_POLICY_REPO_URL, OPAL_POLICY_REPO_POLLING_INTERVAL, server_container
    global OPAL_server_container_name, OPAL_server_7002_port, network_name,OPAL_DATA_TOPICS, private_key, public_key


    # Configuration for OPAL Server
    opal_server_env = {
        "UVICORN_NUM_WORKERS": OPAL_server_uvicorn_num_workers,
        "OPAL_POLICY_REPO_URL": OPAL_POLICY_REPO_URL,
        "OPAL_POLICY_REPO_POLLING_INTERVAL": OPAL_POLICY_REPO_POLLING_INTERVAL,
        "OPAL_AUTH_PRIVATE_KEY": private_key,
        "OPAL_AUTH_PUBLIC_KEY": public_key,
        "OPAL_AUTH_MASTER_TOKEN": OPAL_master_token,
        "OPAL_DATA_CONFIG_SOURCES": f"""{{"config":{{"entries":[{{"url":"{OPAL_SERVER_URL}/policy-data","topics":["{OPAL_DATA_TOPICS}"],"dst_path":"/static"}}]}}}}""",
        "OPAL_LOG_FORMAT_INCLUDE_PID": "true",
        "OPAL_STATISTICS_ENABLED": "true"
    }

    try:
        # Create and start the OPAL Server container
        print("Starting OPAL Server container...")
        server_container = client.containers.run(
            image=OPAL_server_image,
            name=f"{OPAL_server_container_name}",
            ports={"7002/tcp": OPAL_server_7002_port},
            environment=opal_server_env,
            network=network_name,
            detach=True
        )
        print(f"OPAL Server container is running with ID: {server_container.short_id}")

    except requests.exceptions.RequestException as e:
        print(f"HTTP Request failed: {e}")
    except docker.errors.APIError as e:
        print(f"Error with Docker API: {e}")
    except docker.errors.ImageNotFound as e:
        print(f"Error pulling images: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")

def obtain_OPAL_tokens():
    global OPAL_server_7002_port, OPAL_client_token, OPAL_datasource_token
    try:
        token_url = f"http://localhost:{OPAL_server_7002_port}/token"
        headers = {
            "Authorization": f"Bearer {OPAL_master_token}",
            "Content-Type": "application/json"
        }
        data_client = {
            "type": "client"
        }
        data_datasource = {
            "type": "datasource"
        }
        # Fetch the client token
        response = requests.post(token_url, headers=headers, json=data_client)
        response.raise_for_status()
        response_json = response.json()
        OPAL_client_token = response_json.get("token")

        if OPAL_client_token:
            print("OPAL_CLIENT_TOKEN successfully fetched:")
            with open(os.path.join(temp_dir, "./OPAL_CLIENT_TOKEN.tkn"), 'w') as client_token_file:
                client_token_file.write(OPAL_client_token)
            print(OPAL_client_token)
        else:
            print("Failed to fetch OPAL_CLIENT_TOKEN. Response:")
            print(response_json)

        # Fetch the datasource token
        response = requests.post(token_url, headers=headers, json=data_datasource)
        response.raise_for_status()
        response_json = response.json()
        OPAL_datasource_token = response_json.get("token")

        if OPAL_datasource_token:
            print("OPAL_DATASOURCE_TOKEN successfully fetched:")
            with open(os.path.join(temp_dir, "./OPAL_DATASOURCE_TOKEN.tkn"), 'w') as datasource_token_file:
                datasource_token_file.write(OPAL_datasource_token)
            print(OPAL_datasource_token)
        else:
            print("Failed to fetch OPAL_DATASOURCE_TOKEN. Response:")
            print(response_json)

    except requests.exceptions.RequestException as e:
        print(f"HTTP Request failed: {e}")
    except docker.errors.APIError as e:
        print(f"Error with Docker API: {e}")
    except docker.errors.ImageNotFound as e:
        print(f"Error pulling images: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")

def prepare_OPAL_client():

    global OPAL_DATA_TOPICS, OPAL_SERVER_URL, OPAL_client_container_name, OPAL_client_7000_port, OPAL_client_8181_port, client_container

    try:
        # Configuration for OPAL Client
        opal_client_env = {
            "OPAL_DATA_TOPICS": OPAL_DATA_TOPICS,
            "OPAL_SERVER_URL": OPAL_SERVER_URL,
            "OPAL_CLIENT_TOKEN": OPAL_client_token,
            "OPAL_LOG_FORMAT_INCLUDE_PID": "true",
            "OPAL_INLINE_OPA_LOG_FORMAT": "http"
        }

        # Create and start the OPAL Client container
        print("Starting OPAL Client container...")
        client_container = client.containers.run(
            image=OPAL_client_image,
            name= f"{OPAL_client_container_name}",
            ports={"7000/tcp": OPAL_client_7000_port, "8181/tcp": OPAL_client_8181_port},
            environment=opal_client_env,
            network=network_name,
            detach=True
        )
        print(f"OPAL Client container is running with ID: {client_container.short_id}")

    except requests.exceptions.RequestException as e:
        print(f"HTTP Request failed: {e}")
    except docker.errors.APIError as e:
        print(f"Error with Docker API: {e}")
    except docker.errors.ImageNotFound as e:
        print(f"Error pulling images: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")





import argparse
import os

def prepare_args():
    global temp_dir, filename, command, network_name, OPAL_client_8181_port, OPAL_client_7000_port
    global OPAL_POLICY_REPO_POLLING_INTERVAL, OPAL_server_uvicorn_num_workers, OPAL_POLICY_REPO_URL
    global OPAL_server_7002_port, OPAL_DATA_TOPICS, OPAL_SERVER_URL, OPAL_server_container_name, OPAL_client_container_name

    # Initialize argument parser
    parser = argparse.ArgumentParser(description="Setup OPAL test environment.")
    
    # Define arguments
    parser.add_argument("--temp_dir", required=True, help="Path to the temporary directory.")
    parser.add_argument("--network_name", required=True, help="Docker network name (default: opal_test).")
    parser.add_argument("--OPAL_POLICY_REPO_URL", required=True, help="URL for the OPAL policy repository (default: example URL).")
    parser.add_argument("--OPAL_server_7002_port", default=7002, type=int, help="Port for OPAL server (default: 7002).")
    parser.add_argument("--OPAL_client_7000_port", default=7766, type=int, help="Port for OPAL client (default: 7766).")
    parser.add_argument("--OPAL_client_8181_port", default=8181, type=int, help="Port for OPAL client API (default: 8181).")
    parser.add_argument("--OPAL_server_uvicorn_num_workers", default="1", help="Number of Uvicorn workers (default: 1).")
    parser.add_argument("--OPAL_POLICY_REPO_POLLING_INTERVAL", default="50", help="Polling interval for OPAL policy repo (default: 50 seconds).")
    parser.add_argument("--OPAL_DATA_TOPICS", default="policy_data", help="Data topics for OPAL server (default: policy_data).")
    parser.add_argument("--OPAL_server_container_name", default="permit-test-compose-opal-server", help="Container name for OPAL server (default: permit-test-compose-opal-server).")
    parser.add_argument("--OPAL_client_container_name", default="permit-test-compose-opal-client", help="Container name for OPAL client (default: permit-test-compose-opal-client).")
    
    
    # Parse arguments
    args = parser.parse_args()
    
    # Set global variables
    network_name = args.network_name
    OPAL_server_container_name = args.OPAL_server_container_name
    OPAL_client_container_name = args.OPAL_client_container_name
    OPAL_server_uvicorn_num_workers = args.OPAL_server_uvicorn_num_workers
    OPAL_POLICY_REPO_URL = args.OPAL_POLICY_REPO_URL
    OPAL_POLICY_REPO_POLLING_INTERVAL = args.OPAL_POLICY_REPO_POLLING_INTERVAL
    OPAL_server_7002_port = args.OPAL_server_7002_port
    OPAL_DATA_TOPICS = args.OPAL_DATA_TOPICS
    OPAL_client_7000_port = args.OPAL_client_7000_port
    OPAL_client_8181_port = args.OPAL_client_8181_port
    temp_dir = os.path.abspath(args.temp_dir)

    # Ensure temp_dir exists
    os.makedirs(temp_dir, exist_ok=True)

    # Derived global variables
    OPAL_SERVER_URL = f"http://{OPAL_server_container_name}:{OPAL_server_7002_port}"
    command = [
        "ssh-keygen",
        "-t", "rsa",         # Key type
        "-b", "4096",        # Key size
        "-m", "pem",         # PEM format
        "-f", os.path.join(temp_dir, filename),  # Dynamic file name for the key
        "-N", ""             # No password
    ]

if __name__ == "__main__":
    # Call prepare_args to parse arguments and set global variables
    prepare_args()
    
    # Example: Print values to verify global variables
    print("Global variables set:")
    print(f"network_name: {network_name}")
    print(f"OPAL_SERVER_URL: {OPAL_SERVER_URL}")
    print(f"Command for SSH key generation: {command}")

def main():
    prepare_args()

    prepare_keys()
    prepare_network()
    pull_OPAL_images()

    prepare_OPAL_server()

    # Wait for the server to initialize (ensure readiness)
    time.sleep(2)

    obtain_OPAL_tokens()

    prepare_OPAL_client()

if __name__ == "__main__":
    main()
