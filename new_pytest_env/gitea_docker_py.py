import docker

user_name = "ariAdmin2"
email = "Ari2@gmail.com"
password = "Aw123456"
add_admin_user_command = f"/usr/local/bin/gitea admin user create --admin --username {user_name} --email {email} --password {password} --must-change-password=false"
# docker exec -it ffc52c40e5ce /bin/bash /usr/local/bin/gitea admin user create --username ariAdmin --email Ari@gmail.com --password Aw123456 --admin --must-change-password false


def setup_gitea():
    print("Starting Gitea deployment...")

    client = docker.from_env()

    # Pull necessary Docker images
    print("Pulling Docker images...")
    client.images.pull("gitea/gitea:latest")
    client.images.pull("postgres:latest")
    client.images.pull("gitea/gitea:latest-rootless")
    # Create Docker network for communication
    print("Creating Docker network...")
    networks = client.networks.list(names=["gitea-net"])
    if not networks:
        try:
            client.networks.create("gitea-net")
            print("Network 'gitea-net' created.")
        except docker.errors.APIError as e:
            print(f"Error creating network 'gitea-net': {e}")
    else:
        print("Network 'gitea-net' already exists, skipping...")

    # Run PostgreSQL container
    print("Setting up PostgreSQL container...")
    try:
        print("postgress id: " + client.containers.run(
            "postgres:latest",
            name="gitea-db",
            network="gitea-net",
            detach=True,
            environment={
                "POSTGRES_USER": "gitea",
                "POSTGRES_PASSWORD": "gitea123",
                "POSTGRES_DB": "gitea",
            },
            volumes={"gitea-db-data": {"bind": "/var/lib/postgresql/data", "mode": "rw"}},
        ).short_id)
    except docker.errors.APIError:
        print("Container 'gitea-db' already exists, skipping...")

    # Run Gitea container
    print("Setting up Gitea container...")
    import os
    try:
        gitea = client.containers.run(
            "gitea/gitea:latest-rootless",
            name="gitea",
            network="gitea-net",
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
                "INSTALL_LOCK":"true",
            },
            volumes={"gitea-data": {"bind": os.path.abspath("./data"), "mode": "rw"}},
        )
        print(f"gitea id: {gitea.short_id}")
    except docker.errors.APIError:
        print("Container 'gitea' already exists, skipping...")

    print("Gitea deployment completed. Access Gitea at http://localhost:3000")
    try:
        print(gitea.exec_run(add_admin_user_command))
    except docker.errors.APIError:
        print("Container 'gitea' already exists, skipping...")    

if __name__ == "__main__":
    setup_gitea()
