import docker

def pull_docker_image(image_name):
    # Create a Docker client
    client = docker.from_env()

    # Pull the image and stream progress
    print(f"Pulling image: {image_name}")
    try:
        for line in client.api.pull(image_name, stream=True, decode=True):
            # Display the progress messages
            status = line.get("status")
            progress = line.get("progress", "")
            print(f"{status} {progress}".strip())
        print("Image pulled successfully!")
    except docker.errors.APIError as e:
        print(f"An error occurred: {e}")

# Example usage: Pull the "hello-world" image
if __name__ == "__main__":
    image_name = "hello-world:latest"
    pull_docker_image(image_name)
