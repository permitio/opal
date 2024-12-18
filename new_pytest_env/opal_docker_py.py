import docker
import time
import os
import subprocess
import requests
from dotenv import load_dotenv

# Load .env file if it exists
load_dotenv()

# Define the environment variable name
env_var = "FILE_NUMBER"

# Get the current value of FILE_NUMBER, or set it to 1 if it doesn't exist
file_number = int(os.getenv(env_var, "1"))

# Define the directory for storing keys
key_dir = "./opal_test_keys"

# Ensure the directory exists
os.makedirs(key_dir, exist_ok=True)

# Find the next available file number
while True:
    # Construct the filename dynamically with the directory path
    filename = os.path.join(key_dir, f"opal_test_{file_number}")
    if not os.path.exists(filename) and not os.path.exists(f"{filename}.pub"):
        break  # Stop if neither private nor public key exists
    file_number += 1  # Increment the number and try again

# Define the ssh-keygen command with the dynamic filename
command = [
    "ssh-keygen",
    "-t", "rsa",         # Key type
    "-b", "4096",        # Key size
    "-m", "pem",         # PEM format
    "-f", filename,      # Dynamic file name for the key
    "-N", ""             # No password
]

try:
    # Generate the SSH key pair
    subprocess.run(command, check=True)
    print(f"SSH key pair generated successfully! Files: {filename}, {filename}.pub")
    
    # Load the private and public keys into variables
    with open(filename, "r") as private_key_file:
        private_key = private_key_file.read()

    with open(f"{filename}.pub", "r") as public_key_file:
        public_key = public_key_file.read()

    print("Private Key Loaded:")
    print(private_key)
    print("\nPublic Key Loaded:")
    print(public_key)

    # Run 'opal-server generate-secret' and save the output
    OPAL_AUTH_MASTER_TOKEN = subprocess.check_output(["opal-server", "generate-secret"], text=True).strip()
    print(f"OPAL_AUTH_MASTER_TOKEN: {OPAL_AUTH_MASTER_TOKEN}")
    
    # Increment and validate the next file number
    new_file_number = file_number + 1
    while True:
        next_filename = os.path.join(key_dir, f"opal_test_{new_file_number}")
        if not os.path.exists(next_filename) and not os.path.exists(f"{next_filename}.pub"):
            break  # Stop if neither private nor public key exists
        new_file_number += 1  # Increment the number and try again
    
    # Update the environment variable
    os.environ[env_var] = str(new_file_number)  # Update the environment variable for the current process

    # Persist the updated value for future runs
    with open(".env", "w") as env_file:
        env_file.write(f"{env_var}={new_file_number}\n")
        env_file.write(f"OPAL_AUTH_MASTER_TOKEN={OPAL_AUTH_MASTER_TOKEN}\n")
    print(f"Updated {env_var} to {new_file_number} and saved OPAL_AUTH_MASTER_TOKEN")
except subprocess.CalledProcessError as e:
    print(f"Error occurred: {e}")
except Exception as e:
    print(f"Unexpected error: {e}")

# Initialize Docker client
client = docker.DockerClient(base_url="unix://var/run/docker.sock")

# Create a Docker network named 'opal_test'
network_name = "opal_test"
if network_name not in [network.name for network in client.networks.list()]:
    print(f"Creating network: {network_name}")
    client.networks.create(network_name, driver="bridge")

# Configuration for OPAL Server
opal_server_env = {
    "UVICORN_NUM_WORKERS": "1",
    "OPAL_POLICY_REPO_URL": "http://gitea_permit:3000/ariAdmin2/opal-example-policy-repo.git",
    "OPAL_POLICY_REPO_POLLING_INTERVAL": "50",
    "OPAL_AUTH_PRIVATE_KEY": private_key,
    "OPAL_AUTH_PUBLIC_KEY": public_key,
    "OPAL_AUTH_MASTER_TOKEN": OPAL_AUTH_MASTER_TOKEN,
    "OPAL_DATA_CONFIG_SOURCES": f"""{{"config":{{"entries":[{{"url":"http://ari_compose_opal_server_{file_number}:7002/policy-data","topics":["policy_data"],"dst_path":"/static"}}]}}}}""",
    "OPAL_LOG_FORMAT_INCLUDE_PID": "true",
    "OPAL_STATISTICS_ENABLED": "true",
}

try:
    # Pull the required images
    print("Pulling OPAL Server image...")
    client.images.pull("permitio/opal-server:latest")

    print("Pulling OPAL Client image...")
    client.images.pull("permitio/opal-client:latest")

    # Create and start the OPAL Server container
    print("Starting OPAL Server container...")
    server_container = client.containers.run(
        image="permitio/opal-server:latest",
        name=f"ari_compose_opal_server_{file_number}",
        ports={"7002/tcp": 7002},
        environment=opal_server_env,
        network=network_name,
        detach=True
    )
    print(f"OPAL Server container is running with ID: {server_container.short_id}")

    # URL for the OPAL Server token endpoint (using localhost)
    token_url = "http://localhost:7002/token"

    # Authorization headers for the request
    headers = {
        "Authorization": f"Bearer {OPAL_AUTH_MASTER_TOKEN}",
        "Content-Type": "application/json"
    }

    # Payload for the POST request to fetch client token
    data_client = {
        "type": "client"
    }

    # Payload for the POST request to fetch datasource token
    data_datasource = {
        "type": "datasource"
    }

    # Wait for the server to initialize (ensure readiness)
    time.sleep(2)

    # Fetch the client token
    response = requests.post(token_url, headers=headers, json=data_client)
    response.raise_for_status()
    response_json = response.json()
    OPAL_CLIENT_TOKEN = response_json.get("token")

    if OPAL_CLIENT_TOKEN:
        print("OPAL_CLIENT_TOKEN successfully fetched:")
        with open("./OPAL_CLIENT_TOKEN.tkn", 'w') as client_token_file:
            client_token_file.write(OPAL_CLIENT_TOKEN)
        print(OPAL_CLIENT_TOKEN)
    else:
        print("Failed to fetch OPAL_CLIENT_TOKEN. Response:")
        print(response_json)

    # Fetch the datasource token
    response = requests.post(token_url, headers=headers, json=data_datasource)
    response.raise_for_status()
    response_json = response.json()
    OPAL_DATASOURCE_TOKEN = response_json.get("token")

    if OPAL_DATASOURCE_TOKEN:
        print("OPAL_DATASOURCE_TOKEN successfully fetched:")
        with open("./OPAL_DATASOURCE_TOKEN.tkn", 'w') as datasource_token_file:
            datasource_token_file.write(OPAL_DATASOURCE_TOKEN)
        print(OPAL_DATASOURCE_TOKEN)
    else:
        print("Failed to fetch OPAL_DATASOURCE_TOKEN. Response:")
        print(response_json)

    # Configuration for OPAL Client
    opal_client_env = {
        "OPAL_DATA_TOPICS": "policy_data",
        "OPAL_SERVER_URL": f"http://ari_compose_opal_server_{file_number}:7002",
        "OPAL_CLIENT_TOKEN": OPAL_CLIENT_TOKEN,
        "OPAL_LOG_FORMAT_INCLUDE_PID": "true",
        "OPAL_INLINE_OPA_LOG_FORMAT": "http"
    }

    # Create and start the OPAL Client container
    print("Starting OPAL Client container...")
    client_container = client.containers.run(
        image="permitio/opal-client:latest",
        name=f"ari-compose-opal-client_{file_number}",
        ports={"7000/tcp": 7766, "8181/tcp": 8181},
        environment=opal_client_env,
        network=network_name,
        detach=True
    )
    print(f"OPAL Client container is running with ID: {client_container.id}")

except requests.exceptions.RequestException as e:
    print(f"HTTP Request failed: {e}")
except docker.errors.APIError as e:
    print(f"Error with Docker API: {e}")
except docker.errors.ImageNotFound as e:
    print(f"Error pulling images: {e}")
except Exception as e:
    print(f"Unexpected error: {e}")
