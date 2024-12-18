import requests
import subprocess
import asyncio

global _error
_error = False
# Load tokens from files
CLIENT_TOKEN = ""
DATASOURCE_TOKEN = ""

with open("./OPAL_CLIENT_TOKEN.tkn", 'r') as client_token_file:
    CLIENT_TOKEN = client_token_file.read().strip()

with open("./OPAL_DATASOURCE_TOKEN.tkn", 'r') as datasource_token_file:
    DATASOURCE_TOKEN = datasource_token_file.read().strip()

############################################

def publish_data_user_location(src, user):
    """Publish user location data to OPAL."""
    publish_data_user_location_command = (
        f"opal-client publish-data-update --src-url {src} "
        f"-t policy_data --dst-path /users/{user}/location {DATASOURCE_TOKEN}"
    )
    result = subprocess.run(publish_data_user_location_command, shell=True, capture_output=True, text=True)

    # # Debug: Print command and its output
    # print(f"Command: {publish_data_user_location_command}")
    # print("Command output:", result.stdout)
    # print("Command error:", result.stderr)
    if result.returncode != 0:
        print("Failed to update user location!")
    else:
        print(f"Updated with src: {src}")


async def test_authorization(user: str):
    """Test if the user is authorized based on the current policy."""
    url = "http://localhost:8181/v1/data/app/rbac/allow"
    headers = {"Content-Type": "application/json"}
    data = {
        "input": {
            "user": user,
            "action": "read",
            "object": "id123",
            "type": "finance"
        }
    }

    # Send request to OPA
    response = requests.post(url, headers=headers, json=data)

    # # Debug: Print the request and response details
    # print("Request data:", data)
    # print("Response status:", response.status_code)
    allowed = False
    try:
        #print("Response JSON:", response.json())
        if "result" in response.json():
            allowed = response.json()["result"]
            print(f"{user} is {'allowed' if allowed else 'not allowed'}!")
        else:
            print(f"Unexpected response format: {response.json()}")
    except Exception as e:
        print(f"Error parsing response: {e}")
    return allowed


async def test_user_location(user: str, US: bool):
    """Test user location policy."""
    if US:
        publish_data_user_location("https://api.country.is", user)
        print(f"{user}'s location is set to: US")
        print("He now should not be allowed!")
    else:
        publish_data_user_location("https://api.country.is/23.54.6.78", user)
        print(f"{user}'s location is set to: SE")
        print("He now should be allowed!")

    # Wait briefly to ensure OPA processes the update
    await asyncio.sleep(1)  # Adjust delay if necessary

    # Test authorization after updating location
    #print("Testing authorization...")
    if await test_authorization(user) == US:
        return True


############################################

# Main entry point for running the tests
async def main(i):

    for x in range(0,i):
        print()
        if (x % 2) == 0:
            if await test_user_location("bob", False):# Test with location set to SE
                return True
        else:
            if await test_user_location("bob", True):  # Test with location set to US
                return True
            


# Run the asyncio event loop
if __name__ == "__main__":
    _error = asyncio.run(main(5))

    if _error:
        print("finished testing and it was *not* successful")
        print()
        print(_error)
    else:
        print("finished testing and it was successful")


