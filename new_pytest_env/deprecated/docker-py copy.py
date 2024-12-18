import docker
import time
import os
import subprocess
import requests
from dotenv import load_dotenv
import shutil
from git import Repo

# gitea test2 api key: 0ce3308010f9818a746670b414dc334a4149d442

# Initialize Docker client
client = docker.DockerClient(base_url="unix://var/run/docker.sock")

#--------------------------------------variables--------------------------------------------

# Define the environment variable name
env_var = "FILE_NUMBER"

# Define the directory for storing keys
key_dir = "./opal_test_keys"

#------------------------------

# opal
opal_network_name = "opal_test"

#------------------------------

# gitea

gitea_db_image = "postgres:latest"
gitea_rootless_image = "gitea/gitea:latest-rootless"
gitea_root_image = "gitea/gitea:latest"

gitea_network_name = opal_network_name

gitea_container_name = "gitea"

gitea_http_port = 3000
gitea_ssh_port = 2222

gitea_user_uid = 1000
gitea_user_gid = 1000

gitea_db_type = "postgres"
gitea_db_host = "gitea-db:5432"
gitea_db_name = "gitea"
gitea_db_user = "gitea"
gitea_db_password = "gitea123"

gitea_install_lock=True

gitea_db_container_name = "gitea-db"

user_name = "ariAdmin2"
email = "Ari2@gmail.com"
password = "Aw123456"
add_admin_user_command = f"/usr/local/bin/gitea admin user create --admin --username {user_name} --email {email} --password {password} --must-change-password=false"

gitea_db_env={
    "POSTGRES_USER": gitea_db_user,
    "POSTGRES_PASSWORD": gitea_db_password,
    "POSTGRES_DB": gitea_db_name,
}

gitea_env={
    "USER_UID": gitea_user_uid,
    "USER_GID": gitea_user_gid,
    "DB_TYPE": gitea_db_type,
    "DB_HOST": gitea_db_host,
    "DB_NAME": gitea_db_name,
    "DB_USER": gitea_db_user,
    "DB_PASSWD": gitea_db_password,
    "INSTALL_LOCK":gitea_install_lock,
}

#------------------------------

# git

env_var_name = "ITERATION_NUMBER"

repo_name = "opal-example-policy-repo"
repo_url = f"https://github.com/ariWeinberg/{repo_name}.git"
destination_path = f"./{repo_name}"

gitea_base_url = "http://localhost:3000"
gitea_api_token = "0ce3308010f9818a746670b414dc334a4149d442"
gitea_username = "AriAdmin2"
gitea_password = "Aw123456"
gitea_repo_url = f"{gitea_base_url}/api/v1/repos/ariAdmin2/{repo_name}"

#-------------------------------------------------------------------------------------------

def generate_keys(file_number):    
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

#-------------------------------------------

def create_opal_network(_opal_network_name):
    try:
        # Create a Docker network named 'opal_test'
        if _opal_network_name not in [network.name for network in client.networks.list()]:
            print(f"Creating network: {_opal_network_name}")
            client.networks.create(_opal_network_name, driver="bridge")
    except requests.exceptions.RequestException as e:
        print(f"HTTP Request failed: {e}")
    except docker.errors.APIError as e:
        print(f"Error with Docker API: {e}")
    except docker.errors.ImageNotFound as e:
        print(f"Error pulling images: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")


def create_client(_opal_client_token, _file_number):
    try:
        # Configuration for OPAL Client
        opal_client_env = {
            "OPAL_DATA_TOPICS": "policy_data",
            "OPAL_SERVER_URL": f"http://ari_compose_opal_server_{_file_number}:7002",
            "OPAL_CLIENT_TOKEN": _opal_client_token,
            "OPAL_LOG_FORMAT_INCLUDE_PID": "true",
            "OPAL_INLINE_OPA_LOG_FORMAT": "http"}

        # Create and start the OPAL Client container
        print("Starting OPAL Client container...")
        client_container = client.containers.run(
            image="permitio/opal-client:latest",
            name=f"ari-compose-opal-client_{file_number}",
            ports={"7000/tcp": 7766, "8181/tcp": 8181},
            environment=opal_client_env,
            network=opal_network_name,
            detach=True)
        print(f"OPAL Client container is running with ID: {client_container.id}")
    except requests.exceptions.RequestException as e:
        print(f"HTTP Request failed: {e}")
    except docker.errors.APIError as e:
        print(f"Error with Docker API: {e}")
    except docker.errors.ImageNotFound as e:
        print(f"Error pulling images: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")


def pull_opal_images():
    try:
        # Pull the required images
        print("Pulling OPAL Server image...")
        client.images.pull("permitio/opal-server:latest")

        print("Pulling OPAL Client image...")
        client.images.pull("permitio/opal-client:latest")
    except requests.exceptions.RequestException as e:
        print(f"HTTP Request failed: {e}")
    except docker.errors.APIError as e:
        print(f"Error with Docker API: {e}")
    except docker.errors.ImageNotFound as e:
        print(f"Error pulling images: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")


def create_server():
    try:
        # Configuration for OPAL Server
        opal_server_env = {
            "UVICORN_NUM_WORKERS": "1",
            "OPAL_POLICY_REPO_URL": "https://github.com/ariWeinberg/opal-example-policy-repo.git",
            "OPAL_POLICY_REPO_POLLING_INTERVAL": "50",
            "OPAL_AUTH_PRIVATE_KEY": private_key,
            "OPAL_AUTH_PUBLIC_KEY": public_key,
            "OPAL_AUTH_MASTER_TOKEN": OPAL_AUTH_MASTER_TOKEN,
            "OPAL_DATA_CONFIG_SOURCES": """{"config":{"entries":[{"url":"http://ari_compose_opal_server_""" + str(file_number) + """:7002/policy-data","topics":["policy_data"],"dst_path":"/static"}]}}""",
            "OPAL_LOG_FORMAT_INCLUDE_PID": "true"
        }

        # Create and start the OPAL Server container
        print("Starting OPAL Server container...")
        server_container = client.containers.run(
            image="permitio/opal-server:latest",
            name=f"ari_compose_opal_server_{file_number}",
            ports={"7002/tcp": 7002},
            environment=opal_server_env,
            network=opal_network_name,
            detach=True
        )
        print(f"OPAL Server container is running with ID: {server_container.id}")
    except requests.exceptions.RequestException as e:
        print(f"HTTP Request failed: {e}")
    except docker.errors.APIError as e:
        print(f"Error with Docker API: {e}")
    except docker.errors.ImageNotFound as e:
        print(f"Error pulling images: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")


def get_client_token():
    # URL for the OPAL Server token endpoint (using localhost)
    token_url = "http://localhost:7002/token"

    # Authorization headers for the request
    headers = {
        "Authorization": f"Bearer {OPAL_AUTH_MASTER_TOKEN}",  # Replace with your server's authorization token
        "Content-Type": "application/json"
    }

    # Payload for the POST request
    data = {
        "type": "client"
    }


    # Make the POST request to fetch the client token
    response = requests.post(token_url, headers=headers, json=data)

    # Raise an exception if the request was not successful
    response.raise_for_status()

    # Parse the JSON response to extract the token
    response_json = response.json()
    OPAL_CLIENT_TOKEN = response_json.get("token")

    if OPAL_CLIENT_TOKEN:
        print("OPAL_CLIENT_TOKEN successfully fetched:")
        print(OPAL_CLIENT_TOKEN)
    else:
        print("Failed to fetch OPAL_CLIENT_TOKEN. Response:")
        print(response_json)

    return OPAL_CLIENT_TOKEN

#---------------------------------------------------------------------------

def clone_repo(repo_url, destination_path):
    """
    Clone a repository from a given URL to the destination path.
    If the destination path exists, it will be removed first.
    """
    if os.path.exists(destination_path):
        print(f"(git) Folder {destination_path} already exists. Deleting it...")
        shutil.rmtree(destination_path)
    try:
        Repo.clone_from(repo_url, destination_path)
        print(f"(git) Repository cloned successfully to {destination_path}")
    except Exception as e:
        print(f"(git) An error occurred while cloning: {e}")

def create_gitea_repo(base_url, api_token, repo_name, private=False):
    """
    Create a repository in Gitea.
    If the repository already exists, return its URL.
    """
    url = f"{base_url}/api/v1/{user}/repos"
    headers = {"Authorization": f"token {api_token}"}
    data = {"name": repo_name, "private": private}

    response = requests.post(url, json=data, headers=headers)
    if response.status_code == 201:
        repo_data = response.json()
        print(f"(git) Repository created: {repo_data['html_url']}")
        return repo_data['clone_url']
    elif response.status_code == 409:  # Repo already exists
        print(f"(git) Repository '{repo_name}' already exists in Gitea.")
        return f"{base_url}/{repo_name}.git"
    else:
        raise Exception(f"Failed to create or fetch repository: {response.json()}")

def create_branch(repo_path, branch_name, base_branch="master"):
    """
    Create a new branch in the local repository based on a specified branch.
    """
    try:
        repo = Repo(repo_path)
        # Ensure the base branch is checked out
        repo.git.checkout(base_branch)

        # Create the new branch if it doesn't exist
        if branch_name not in repo.heads:
            new_branch = repo.create_head(branch_name, repo.heads[base_branch].commit)
            print(f"(git) Branch '{branch_name}' created from '{base_branch}'.")
        else:
            print(f"(git) Branch '{branch_name}' already exists.")

        # Checkout the new branch
        repo.git.checkout(branch_name)
        print(f"(git) Switched to branch '{branch_name}'.")
    except Exception as e:
        print(f"(git) An error occurred while creating the branch: {e}")

def push_to_gitea_with_credentials(cloned_repo_path, gitea_repo_url, username, password, remote_name="gitea"):
    """
    Push the cloned repository to a Gitea repository with credentials included.
    """
    try:
        # Embed credentials in the Gitea URL
        auth_repo_url = gitea_repo_url.replace("://", f"://{username}:{password}@")

        # Open the existing repository
        repo = Repo(cloned_repo_path)

        # Add the Gitea repository as a remote if not already added
        if remote_name not in [remote.name for remote in repo.remotes]:
            repo.create_remote(remote_name, auth_repo_url)
            print(f"(git) Remote '{remote_name}' added with URL: {auth_repo_url}")
        else:
            print(f"(git) Remote '{remote_name}' already exists.")

        # Push all branches to the remote
        remote = repo.remotes[remote_name]
        remote.push(refspec="refs/heads/*:refs/heads/*")
        print(f"(git) All branches pushed to {auth_repo_url}")

        # Push all tags to the remote
        remote.push(tags=True)
        print(f"(git) All tags pushed to {auth_repo_url}")

    except Exception as e:
        print(f"(git) An error occurred while pushing: {e}")

def check_gitea_repo_exists(gitea_url: str, owner: str, repo_name: str, token: str = None) -> bool:
    """
    Check if a Gitea repository exists.

    Args:
        gitea_url (str): Base URL of the Gitea instance (e.g., 'https://gitea.example.com').
        owner (str): Owner of the repository (user or organization).
        repo_name (str): Name of the repository.
        token (str): Optional Personal Access Token for authentication.

    Returns:
        bool: True if the repository exists, False otherwise.
    """
    # Construct the API URL
    api_url = f"{gitea_url}/api/v1/repos/{owner}/{repo_name}"

    # Set headers for authentication if token is provided
    headers = {"Authorization": f"token {token}"} if token else {}

    try:
        response = requests.get(api_url, headers=headers)

        if response.status_code == 200:
            return True  # Repository exists
        elif response.status_code == 404:
            return False  # Repository does not exist
        else:
            print(f"Unexpected response: {response.status_code} - {response.text}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"Error connecting to Gitea: {e}")
        return False

def get_highest_branch_number(gitea_repo_url: str, api_token: str):
    """
    Retrieve the highest numbered branch in the Gitea repository.
    """
    try:
        url = f"{gitea_repo_url}/branches"
        headers = {"Authorization": f"token {api_token}"}

        response = requests.get(url, headers=headers)

        if response.status_code != 200:
            raise Exception(f"Failed to fetch branches: {response.json()}")

        branches = response.json()
        max_number = 0
        for branch in branches:
            branch_name = branch["name"]
            if branch_name.startswith("test_"):
                try:
                    branch_number = int(branch_name.split("_")[1])
                    max_number = max(max_number, branch_number)
                except ValueError:
                    continue  # Ignore branches with invalid number format

        return max_number
    except Exception as e:
        print(f"(git) Error retrieving branches: {e}")
        return 0

def manage_iteration_number(env_var_name, gitea_repo_url, api_token):
    """
    Manage the iteration number stored in an environment variable.
    Ensure it's higher than any branch number in the Gitea repository.
    """
    # Get the iteration number from the environment variable or initialize it
    iteration_number = int(os.getenv(env_var_name, 0))

    # Ensure iteration_number is higher than the highest branch number in Gitea
    if check_gitea_repo_exists(gitea_base_url, user_name, repo_name, gitea_api_token):
        highest_branch_number = get_highest_branch_number(gitea_repo_url, api_token)
        iteration_number = max(iteration_number, highest_branch_number + 1)

    # Update the environment variable
    os.environ[env_var_name] = str(iteration_number)
    return iteration_number

def clone_github_to_gitea(_env_var_name, _gitea_repo_url, _gitea_api_token, _destination_path, _repo_url, _gitea_base_url, _repo_name, _gitea_username, _gitea_password):
    # Step 1: Manage iteration number
    iteration_number = manage_iteration_number(_env_var_name, _gitea_repo_url, _gitea_api_token)
    branch_name = f"test_{iteration_number}"

    # Step 2: Clone the repository from GitHub
    clone_repo(_repo_url, _destination_path)

    # Step 3: Check if the repository exists in Gitea, create it if not
    try:
        create_gitea_repo(_gitea_base_url, _gitea_api_token, _repo_name)
    except Exception as e:
        print(f"(git) Error while creating Gitea repository: {e}")

    # Step 4: Create a new branch in the local repository
    create_branch(_destination_path, branch_name)

    # Step 5: Push the repository to Gitea, including all branches
    push_to_gitea_with_credentials(_destination_path, f"{_gitea_base_url}/{_gitea_username}/{_repo_name}.git", _gitea_username, _gitea_password)

    # Increment the iteration number for the next run
    iteration_number += 1
    os.environ[_env_var_name] = str(iteration_number)

    # Return the link to the Gitea repository with the specific branch
    branch_url = f"{_gitea_base_url}/{_gitea_username}/{_repo_name}/src/branch/{branch_name}"
    print(f"(git) Repository and branch created: {branch_url}")
    return branch_url

#-------------------------------------------------------------------------

def pull_gitea_images(*images):
    # Pull necessary Docker images
    print("(gitea) Pulling Docker images...")
    for img in images:
        print(f"    pulling image: {img}")
        client.images.pull(img)
        print(f"    {img} pulled successfuly")
    print("(gitea) finished pulling images. mooving on....")
        
def create_gitea_db(_gitea_db_image, _gitea_db_container_name, _gitea_network_name, _environment):
    # Run PostgreSQL container
    print("(gitea)(DB) Setting up PostgreSQL container...")
    try:
        gitea_db = client.containers.run(_gitea_db_image, name=_gitea_db_container_name, network=_gitea_network_name, detach=True,
        environment=_environment,
        volumes={"gitea-db-data": {"bind": os.path.abspath("./data/DB"), "mode": "rw"}},)
        print("(gitea)(DB) postgress id: " + gitea_db.short_id)
    except docker.errors.APIError:
        print("(gitea)(DB) Container 'gitea-db' already exists, skipping...")
    return gitea_db

def create_gitea(_gitea_rootless_image, _gitea_container_name, _gitea_network_name, _gitea_http_port, _gitea_ssh_port, _environment):
    # Run Gitea container
    print("(gitea)(gitea) Setting up Gitea container...")
    try:
        gitea = client.containers.run(_gitea_rootless_image, name=_gitea_container_name, network=_gitea_network_name,
                                    detach=True,
                                    ports={"3000/tcp": _gitea_http_port, "22/tcp": _gitea_ssh_port},
            environment=_environment,
            volumes={"gitea-data": {"bind": os.path.abspath("./data/gitea"), "mode": "rw"}},
        )
        print(f"(gitea)(gitea) gitea id: {gitea.short_id}")
    except docker.errors.APIError:
        print("(gitea)(gitea) Container 'gitea' already exists, skipping...")
    return gitea

def Config_gitea_user(_gitea, _add_admin_user_command):
    try:
        print(f"(gitea)(gitea) {_gitea.exec_run(_add_admin_user_command)}")
    except docker.errors.APIError:
        print(f"(gitea)(gitea) user {user_name} already exists, skipping...")   
#---------------------------------------------

def pull_images():
    pull_gitea_images(gitea_db_image, gitea_root_image, gitea_rootless_image)
    pull_opal_images()

if __name__ == "__main__":
    # Load .env file if it exists
    load_dotenv()

    # Get the current value of FILE_NUMBER, or set it to 1 if it doesn't exist
    file_number = int(os.getenv(env_var, "1"))

    generate_keys(file_number)


    pull_images()


    print("(gitea) Starting Gitea deployment...")
    
    gitea_db =  create_gitea_db(gitea_db_image, gitea_db_container_name, gitea_network_name, gitea_db_env)
    
    gitea = create_gitea(gitea_rootless_image, gitea_container_name, gitea_network_name, gitea_http_port, gitea_ssh_port, gitea_env)


    print("waiting for gitea to warm up.")
    time.sleep(5)

    Config_gitea_user(gitea, add_admin_user_command)

    print("waiting for gitea to warm up.")
    time.sleep(5)

    print(f"(gitea) Gitea deployment completed. Access Gitea at http://localhost:{gitea_http_port}")


    print("(git) Starting policy repo creation...")

    clone_github_to_gitea(env_var_name, gitea_repo_url, gitea_api_token, destination_path, repo_url, gitea_base_url, repo_name, gitea_username, gitea_password)

    print("(git) policy repo created successfuly and is ready to use...")


    create_opal_network(opal_network_name)

    create_server()

    # Wait for the server to initialize (ensure readiness)
    time.sleep(2)

    opal_client_token = get_client_token()
    create_client(opal_client_token, file_number)
