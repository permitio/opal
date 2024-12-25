import pytest
import docker
import requests
import os
import shutil
from git import Repo
import time

from deploy.gitea import gitea

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


    a = Network().name = "ababa"
    

    
    c = gitea("gitea_test_1", 3000, 2222, "gitea/gitea:latest-rootless", 1000, 1000, a)


    yield {
        "temp_dir": TEMP_DIR,
        "access_token": ACCESS_TOKEN,
    }
