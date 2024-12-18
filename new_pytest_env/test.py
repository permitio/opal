import requests
import subprocess
import asyncio
import os

# Global variable to track errors
global _error
_error = False

# Load tokens from files
CLIENT_TOKEN = ""
DATASOURCE_TOKEN = ""

# Read client token from file
with open("./OPAL_CLIENT_TOKEN.tkn", 'r') as client_token_file:
    CLIENT_TOKEN = client_token_file.read().strip()

# Read datasource token from file
with open("./OPAL_DATASOURCE_TOKEN.tkn", 'r') as datasource_token_file:
    DATASOURCE_TOKEN = datasource_token_file.read().strip()

############################################

def publish_data_user_location(src, user):
    """Publish user location data to OPAL."""
    # Construct the command to publish data update
    publish_data_user_location_command = (
        f"opal-client publish-data-update --src-url {src} "
        f"-t policy_data --dst-path /users/{user}/location {DATASOURCE_TOKEN}"
    )
    
    # Execute the command
    result = subprocess.run(
        publish_data_user_location_command, shell=True, capture_output=True, text=True
    )

    # Check command execution result
    if result.returncode != 0:
        print("Error: Failed to update user location!")
    else:
        print(f"Successfully updated user location with source: {src}")

async def test_authorization(user: str):
    """Test if the user is authorized based on the current policy."""
    # URL of the OPA endpoint
    url = "http://localhost:8181/v1/data/app/rbac/allow"
    
    # HTTP headers and request payload
    headers = {"Content-Type": "application/json"}
    data = {
        "input": {
            "user": user,
            "action": "read",
            "object": "id123",
            "type": "finance"
        }
    }

    # Send POST request to OPA
    response = requests.post(url, headers=headers, json=data)

    allowed = False
    try:
        # Parse the JSON response
        if "result" in response.json():
            allowed = response.json()["result"]
            print(f"Authorization test result: {user} is {'ALLOWED' if allowed else 'NOT ALLOWED'}.")
        else:
            print(f"Warning: Unexpected response format: {response.json()}")
    except Exception as e:
        print(f"Error: Failed to parse authorization response: {e}")
    
    return allowed

async def test_user_location(user: str, US: bool):
    """Test user location policy based on US or non-US settings."""
    # Update user location based on the provided country flag
    if US:
        publish_data_user_location("https://api.country.is/8.8.8.8", user)
        print(f"{user}'s location set to: US. Expected outcome: NOT ALLOWED.")
    else:
        publish_data_user_location("https://api.country.is/23.54.6.78", user)
        print(f"{user}'s location set to: SE. Expected outcome: ALLOWED.")

    # Allow time for the policy engine to process the update
    await asyncio.sleep(1)

    # Test authorization after updating the location
    if await test_authorization(user) == US:
        return True

async def test_data(iterations):
    """Run the user location policy tests multiple times."""
    for i in range(iterations):
        print(f"\nRunning test iteration {i + 1}...")
        if i % 2 == 0:
            # Test with location set to SE (non-US)
            if await test_user_location("bob", False):
                return True
        else:
            # Test with location set to US
            if await test_user_location("bob", True):
                return True

def update_policy(country_value):
    """Update the policy file dynamically."""
    # Get the directory of the current script
    current_directory = os.path.dirname(os.path.abspath(__file__))

    # Path to the external script for policy updates
    second_script_path = os.path.join(current_directory, "gitea_branch_update.py")

    # Command arguments to update the policy
    args = [
        "python",  # Python executable
        second_script_path,  # Script path
        "--file_name", 
        "rbac.rego",
        "--file_content",
        (
            "package app.rbac\n"
            "default allow = false\n\n"
            "# Allow the action if the user is granted permission to perform the action.\n"
            "allow {\n"
            "\t# unless user location is outside US\n"
            "\tcountry := data.users[input.user].location.country\n"
            "\tcountry == \"" + country_value + "\"\n"
            "}"
        ),
    ]

    # Execute the external script to update the policy
    subprocess.run(args)

    # Allow time for the update to propagate
    import time
    time.sleep(80)

async def main(iterations):
    """Main function to run tests with different policy settings."""
    # Update policy to allow only non-US users
    print("Updating policy to allow only users from SE...")
    update_policy("SE")

    if await test_data(iterations):
        return True

    print("Policy updated to allow only US users. Re-running tests...")

    # Update policy to allow only US users
    update_policy("US")

    if not await test_data(iterations):
        return True

# Run the asyncio event loop
if __name__ == "__main__":
    _error = asyncio.run(main(3))

    if _error:
        print("Finished testing: NOT SUCCESSFUL.")
    else:
        print("Finished testing: SUCCESSFUL.")
