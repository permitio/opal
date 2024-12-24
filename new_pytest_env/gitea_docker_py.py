import argparse
import docker
import os
import time

# Globals for configuration
PERSISTENT_VOLUME = ""
temp_dir = ""
user_name = ""
email = ""
password = ""

network_name = ""

user_UID = ""
user_GID = ""

ADD_ADMIN_USER_COMMAND = ""
CREATE_ACCESS_TOKEN_COMMAND = ""

# Function to check if Gitea is ready
def is_gitea_ready(container):
    logs = container.logs().decode("utf-8")
    return "Listen: http://0.0.0.0:3000" in logs

# Function to set up Gitea with Docker
def setup_gitea():
    global PERSISTENT_VOLUME, temp_dir, ADD_ADMIN_USER_COMMAND, CREATE_ACCESS_TOKEN_COMMAND, network_name, user_GID, user_UID

    print(f"Using temp_dir: {temp_dir}")
    print(f"Using PERSISTENT_VOLUME: {PERSISTENT_VOLUME}")

    print("Starting Gitea deployment...")

    # Initialize Docker client
    client = docker.from_env()

    # Create a Docker network named 'opal_test'
    if network_name not in [network.name for network in client.networks.list()]:
        print(f"Creating network: {network_name}")
        client.networks.create(network_name, driver="bridge")

    # Pull necessary Docker images
    print("Pulling Docker images...")
    client.images.pull("gitea/gitea:latest-rootless")

    # Set up Gitea container
    print("Setting up Gitea container...")
    try:
        gitea = client.containers.run(
            "gitea/gitea:latest-rootless",
            name="gitea_permit",
            network=network_name,
            detach=True,
            ports={"3000/tcp": 3000, "22/tcp": 2222},
            environment={
                "USER_UID": user_UID,
                "USER_GID": user_GID,
                "DB_TYPE": "sqlite3",    # Use SQLite
                "DB_PATH": "./",
                "INSTALL_LOCK": "true",
            },
        )
        print(f"Gitea container is running with ID: {gitea.short_id}")

        # Wait for Gitea to initialize
        print("Waiting for Gitea to initialize...")
        for _ in range(30):  # Check for up to 30 seconds
            if is_gitea_ready(gitea):
                print("Gitea is ready!")
                break
            time.sleep(1)
        else:
            print("Gitea initialization timeout. Check logs for details.")
            return

        # Add admin user to Gitea
        print("Creating admin user...")
        result = gitea.exec_run(ADD_ADMIN_USER_COMMAND)
        print(result.output.decode("utf-8"))

        access_token = gitea.exec_run(CREATE_ACCESS_TOKEN_COMMAND).output.decode("utf-8").removesuffix("\n")
        print(access_token)
        if access_token != "Command error: access token name has been used already":
            with open(os.path.join(temp_dir, "gitea_access_token.tkn"), 'w') as gitea_access_token_file:
                gitea_access_token_file.write(access_token)
    except docker.errors.APIError as e:
        print(f"Error: {e.explanation}")
    except Exception as e:
        print(f"Unexpected error: {e}")

    print("Gitea deployment completed. Access Gitea at http://localhost:3000")


def main():
    global PERSISTENT_VOLUME, temp_dir, user_name, email, password, ADD_ADMIN_USER_COMMAND, CREATE_ACCESS_TOKEN_COMMAND, network_name, user_UID, user_GID

    parser = argparse.ArgumentParser(description="Setup Gitea with admin user and persistent volume.")
    parser.add_argument("--temp_dir", required=True, help="Path to the temporary directory.")
    parser.add_argument("--user_name", required=True, help="Admin username.")
    parser.add_argument("--email", required=True, help="Admin email address.")
    parser.add_argument("--password", required=True, help="Admin password.")
    parser.add_argument("--network_name", required=True, help="network name.")
    parser.add_argument("--user_UID", required=True, help="user UID.")
    parser.add_argument("--user_GID", required=True, help="user GID.")
    args = parser.parse_args()

    # Assign globals
    temp_dir = args.temp_dir
    user_name = args.user_name
    email = args.email
    password = args.password

    network_name = args.network_name

    user_UID = args.user_UID
    user_GID = args.user_GID



    print(temp_dir)
    print(user_name)
    print(email)
    print(password)

    PERSISTENT_VOLUME = os.path.expanduser("~/gitea_data")

    ADD_ADMIN_USER_COMMAND = f"/usr/local/bin/gitea admin user create --admin --username {user_name} --email {email} --password {password} --must-change-password=false"
    CREATE_ACCESS_TOKEN_COMMAND = f"gitea admin user generate-access-token --username {user_name} --raw --scopes all"

    # Ensure the persistent volume directory exists
    if not os.path.exists(PERSISTENT_VOLUME):
        os.makedirs(PERSISTENT_VOLUME)

    # Run setup
    setup_gitea()


if __name__ == "__main__":
    main()
