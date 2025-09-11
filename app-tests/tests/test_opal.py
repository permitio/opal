import pytest
import time
import requests
import subprocess

def test_push_policy(prepare_policy_repo):
    """Test pushing a new policy to OPAL."""
    repo_branch = prepare_policy_repo
    policy_name = "test_policy"
    rego_file = f"{policy_name}.rego"

    subprocess.run(["touch", f"opal-tests-policy-repo/{rego_file}"], check=True)
    subprocess.run(["git", "add", rego_file], cwd="opal-tests-policy-repo", check=True)
    subprocess.run(["git", "commit", "-m", f"Add {rego_file}"], cwd="opal-tests-policy-repo", check=True)
    subprocess.run(["git", "push"], cwd="opal-tests-policy-repo", check=True)

    webhook_data = {
        "gitEvent": "git.push",
        "repository": {"git_url": "git@github.com:permitio/opal-tests-policy-repo.git"}
    }
    
    response = requests.post(
        "http://localhost:7002/webhook",
        json=webhook_data,
        headers={"Content-Type": "application/json", "x-webhook-token": "xxxxx"}
    )
    time.sleep(5)

    assert response.status_code == 200


def test_data_publish():
    """Test publishing data via OPAL client."""
    user = "bob"
    response = subprocess.run(
        ["opal-client", "publish-data-update", "--src-url", "https://api.country.is/23.54.6.78",
         "-t", "policy_data", "--dst-path", f"/users/{user}/location"],
        capture_output=True, text=True
    )
    time.sleep(5)

    assert "Event Published Successfully" in response.stdout, f"Unexpected response: {response.stdout}"


def test_statistics():
    """Test statistics API."""
    for port in range(7002, 7004):
        response = requests.get(
            f"http://localhost:{port}/stats",
            headers={"Authorization": "Bearer xxxxx"}
        )
        print("📌 Debug: OPAL Server Response ->", response.text)
        assert response.status_code == 200, f"Unexpected response: {response.text}"
        assert '"client_count":' in response.text, "Statistics response does not contain expected client count"
        assert '"server_count":' in response.text, "Statistics response does not contain expected server count"

