import pytest
import docker
import requests
import os
import shutil
from git import Repo
import time

from deploy.gitea import Gitea
from deploy.server import OPALServer

from testcontainers.core.network import Network
# Initialize Docker client
client = docker.from_env()



# Define current_folder as a global variable
current_folder = os.path.dirname(os.path.abspath(__file__))

def cleanup(_temp_dir):
        if os.path.exists(_temp_dir):
            shutil.rmtree(_temp_dir)

def prepare_temp_dir():
    """
    Creates a 'temp' folder next to the running script. If it exists, deletes it recursively and recreates it.

    :return: Absolute path of the created 'temp' folder.
    """
    temp_dir = os.path.join(current_folder, 'temp')

    cleanup(temp_dir)

    os.makedirs(temp_dir)
    data_dir = os.path.join(temp_dir, 'data')
    os.makedirs(data_dir)

    return temp_dir


#########
# gitea
#########

# Global configuration variables
TEMP_DIR = prepare_temp_dir()
GITEA_BASE_URL = "http://localhost:3000"
USER_NAME = "permitAdmin"
EMAIL = "admin@permit.io"
PASSWORD = "Aa123456"
NETWORK_NAME = "opal_test"
USER_UID = "1000"
USER_GID = "1000"

ACCESS_TOKEN = None

GITEA_3000_PORT = 3000
GITEA_2222_PORT = 2222

GITEA_CONTAINER_NAME = "gitea_permit"
GITEA_IMAGE = "gitea/gitea:latest-rootless"



gitea_container = None
#########
# repo
#########




# Replace these with your Gitea server details and personal access token
gitea_base_url = f"http://localhost:{GITEA_3000_PORT}/api/v1"  # Replace with your Gitea server URL

temp_dir = TEMP_DIR

data_dir = current_folder

user_name = USER_NAME

access_token = ACCESS_TOKEN




repo_name = "opal-example-policy-repo"
source_rbac_file = os.path.join(data_dir, "rbac.rego")
clone_directory = os.path.join(temp_dir, "test-repo")
private = False
description = "This is a test repository created via API."



#########
# main
#########

@pytest.fixture(scope="session")
def deploy():
    """
    Deploys Gitea and initializes the repository.
    """


    net = Network().create()
    

        
    # Initialize Gitea with a specific repository
    gitea_container = Gitea(
        GITEA_CONTAINER_NAME="test_container",
        repo_name="test_repo",
        temp_dir=os.path.join(os.path.dirname(__file__), "temp"),
        data_dir=os.path.dirname(__file__),
        gitea_base_url="http://localhost:3000"
    ).with_network(net).with_network_aliases("gitea")

    # Dynamically generate the admin token after deployment
    gitea_container.deploy_gitea()

    print("Gitea container deployed and running.")

    # Initialize the repository
    gitea_container.init_repo()

    print("Gitea repo initialized successfully.")


    opal_server = OPALServer(
        image="permitio/opal-server:latest",
        container_name="permit-opal-server",
        network_name="opal_test",
        port=7002,
        uvicorn_workers="1",
        policy_repo_url="http://gitea:3000/permitAdmin/test_repo.git",
        polling_interval="10",
        private_key="""-----BEGIN RSA PRIVATE KEY-----
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
-----END RSA PRIVATE KEY-----""",
        public_key="ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQC+Uk4fLwMkKYrL4zrG9Rek5NasOD0updTPkf9+LVTdj5Lezay+RGR4pnbAk14i4qO4FjqNSGg7vvj5vbN8I0xxmyZQrebP4wTp+5JN3kw+Fdup4QiqsGO7YtargefQ/RZhL96MH4JrskLgkfpTyL4A2tm8F5H/a7kKbHXsg89jcFBZnjciSU92PvXBlNBfGKWGUu5ONCO4/Pq6A9XLArHwtsO/uh+3dWRxw4vR2AU2WXs0pb/V4BLAwW/nsmidicwr1+qNv0RSz6oyFOI41KV0lr9Amy33D5YlzvviZ32wuctH6avu96tTayDQ1rR+Cxk44LcAjBcwu34aGomEfeo6OgUnOb4qGRdBwu7BhjZ1RP1kN1Kp9SANAa0E8Q9/fDTaP6ny9dzfH94DnvaPPM6z6e/xCEqbUZ5u7QKiVQ/xQ+r9PloGmx6EiqYn1kI23Qn428+X5IYdx2vGEM/dogA9VgC6HW17yZ/+qhux72b49AkuJ7O7OqIMoZN/KkVnyN1+ct3qicymmkWQou+gpqnPE9VK1nqIZCNomq54RxtllBVKbgD8rnm3VI1o9raa6j/mm3y4CJZ68aX13sTp0hpKLGKjtjQZfq9xQ2M7iyWo5hl5MEFzfaaI/IblDKCwOvC/ntWFfijnhG8pE+vqJ21J2U76mCVXfY5O1LV+X7keiQ== ari@weinberg-lap",
        master_token="Ctuu95wYrPDFQjG7-vYA17Gxs0jKKS9joOVvSnwL5eI",
        data_topics="policy_data"#,
        #broadcast_uri="postgres://user:password@hostname:5432/database",
    )

    opal_server.start_server(net)#.with_network(net).with_network_aliases("server")

    time.sleep(10)
    # Fetch OPAL tokens (method exists but is not called automatically)
    tokens = opal_server.obtain_OPAL_tokens()

    # Container will persist and stay running

    time.sleep(100)
    yield {
        "temp_dir": TEMP_DIR,
        "access_token": ACCESS_TOKEN,
    }
