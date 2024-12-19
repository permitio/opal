import docker
import os
import time

PERSISTENT_VOLUME = os.path.expanduser("~/gitea_data")

# Create a persistent volume (directory) if it doesn't exist
if not os.path.exists(PERSISTENT_VOLUME):
    os.makedirs(PERSISTENT_VOLUME)

# Configuration for admin user
user_name = "permitAdmin2"
email = "permit@gmail.com"
password = "AA123456"
add_admin_user_command = f"/usr/local/bin/gitea admin user create --admin --username {user_name} --email {email} --password {password} --must-change-password=false"
create_access_token_command = f" gitea admin user generate-access-token --username {user_name} --raw --scopes all"

#create_access_token_command = f"sqlite3 /var/lib/gitea/data/gitea.db \"DELETE FROM access_token WHERE name = 'gitea-admin' AND user_id = (SELECT id FROM user WHERE name = '{user_name}');\" && gitea admin user generate-access-token --username {user_name} --raw --scopes all"

# Function to check if Gitea is ready
def is_gitea_ready(container):
    logs = container.logs().decode("utf-8")
    return "Listen: http://0.0.0.0:3000" in logs

# Function to set up Gitea with Docker
def setup_gitea():
    print("Starting Gitea deployment...")

    # Initialize Docker client
    client = docker.from_env()

    # Create a Docker network named 'opal_test'
    network_name = "opal_test"
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
                "USER_UID": "1000",
                "USER_GID": "1000",
                "DB_TYPE": "sqlite3",    # Use SQLite
                "DB_PATH": "/data/gitea.db",  # Path for the SQLite database
                "INSTALL_LOCK": "true",
            },
            volumes={
                PERSISTENT_VOLUME: {"bind": "/data", "mode": "rw"},
                                os.path.abspath("./data"): {  # Local directory for persistence
                    "bind": "/var/lib/gitea",  # Container path
                    "mode": "rw"
                }
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
        result = gitea.exec_run(add_admin_user_command)
        print(result.output.decode("utf-8"))

        access_token = gitea.exec_run(create_access_token_command).output.decode("utf-8").removesuffix("\n")
        print(access_token)
        if access_token != "Command error: access token name has been used already":
            with open("./gitea_access_token.tkn",'w') as gitea_access_token_file:
                gitea_access_token_file.write(access_token)
    except docker.errors.APIError as e:
        print(f"Error: {e.explanation}")
    except Exception as e:
        print(f"Unexpected error: {e}")

    print("Gitea deployment completed. Access Gitea at http://localhost:3000")

if __name__ == "__main__":
    setup_gitea()
