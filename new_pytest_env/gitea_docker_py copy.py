import docker

# Configuration for admin user
user_name = "ariAdmin2"
email = "Ari2@gmail.com"
password = "Aw123456"
add_admin_user_command = f"/usr/local/bin/gitea admin user create --admin --username {user_name} --email {email} --password {password} --must-change-password=false"

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
    client.images.pull("gitea/gitea:latest")
    client.images.pull("postgres:latest")
    client.images.pull("gitea/gitea:latest-rootless")

    # Set up PostgreSQL container
    print("Setting up PostgreSQL container...")
    try:
        postgres_container = client.containers.run(
            "postgres:latest",
            name="gitea-db",
            network=network_name,
            detach=True,
            environment={
                "POSTGRES_USER": "gitea",
                "POSTGRES_PASSWORD": "gitea123",
                "POSTGRES_DB": "gitea",
            },
            volumes={"gitea-db-data": {"bind": "/var/lib/postgresql/data", "mode": "rw"}},
        )
        print(f"PostgreSQL container is running with ID: {postgres_container.short_id}")
    except docker.errors.APIError:
        print("Container 'gitea-db' already exists, skipping...")

    # Set up Gitea container
    print("Setting up Gitea container...")
    import os
    try:
        gitea = client.containers.run(
            "gitea/gitea:latest-rootless",
            name="gitea",
            network=network_name,
            detach=True,
            ports={"3000/tcp": 3000, "22/tcp": 2222},
            environment={
                "USER_UID": "1000",
                "USER_GID": "1000",
                "DB_TYPE": "postgres",
                "DB_HOST": "gitea-db:5432",
                "DB_NAME": "gitea",
                "DB_USER": "gitea",
                "DB_PASSWD": "gitea123",
                "INSTALL_LOCK": "true",
            },
            volumes={
                os.path.abspath("./data"): {  # Local directory for persistence
                    "bind": "/var/lib/gitea",  # Container path
                    "mode": "rw"
                }
            }
        )
        print(f"Gitea container is running with ID: {gitea.short_id}")

        # Add admin user to Gitea
        print("Creating admin user...")
        print(gitea.exec_run(add_admin_user_command))
    except docker.errors.APIError:
        print("Container 'gitea' already exists, skipping...")

    print("Gitea deployment completed. Access Gitea at http://localhost:3000")

if __name__ == "__main__":
    setup_gitea()
