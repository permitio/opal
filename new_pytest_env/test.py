# import requests
# import subprocess
# import asyncio
# import os
# import argparse

# # Global variable to track errors
# global _error
# _error = False

# # Load tokens from files
# CLIENT_TOKEN = None
# DATASOURCE_TOKEN = None



# ip_to_location_base_url = "https://api.country.is/"

# US_ip = "8.8.8.8"
# SE_ip = "23.54.6.78"


# OPA_base_url = None
# policy_URI = None


# policy_url = None




# policy_file_path = None

# ips = None
# countries = None



# # Get the directory of the current script
# current_directory = None

# # Path to the external script for policy updates
# second_script_path = None


# gitea_password = None
# gitea_user_name = None
# gitea_repo_url = None 
# temp_dir = None 
# branches = None


# ############################################

# def publish_data_user_location(src, user):
#     """Publish user location data to OPAL."""
#     # Construct the command to publish data update
#     publish_data_user_location_command = (
#         f"opal-client publish-data-update --src-url {src} "
#         f"-t policy_data --dst-path /users/{user}/location {DATASOURCE_TOKEN}"
#     )
    
#     # Execute the command
#     result = subprocess.run(
#         publish_data_user_location_command, shell=True, capture_output=True, text=True
#     )

#     # Check command execution result
#     if result.returncode != 0:
#         print("Error: Failed to update user location!")
#     else:
#         print(f"Successfully updated user location with source: {src}")

# async def test_authorization(user: str):
#     """Test if the user is authorized based on the current policy."""

#     global policy_url
    
#     # HTTP headers and request payload
#     headers = {"Content-Type": "application/json" }
#     data = {
#         "input": {
#             "user": user,
#             "action": "read",
#             "object": "id123",
#             "type": "finance"
#         }
#     }

#     # Send POST request to OPA
#     response = requests.post(policy_url, headers=headers, json=data)

#     allowed = False
#     try:
#         # Parse the JSON response
#         if "result" in response.json():
#             allowed = response.json()["result"]
#             print(f"Authorization test result: {user} is {'ALLOWED' if allowed else 'NOT ALLOWED'}.")
#         else:
#             print(f"Warning: Unexpected response format: {response.json()}")
#     except Exception as e:
#         print(f"Error: Failed to parse authorization response: {e}")
    
#     return allowed

# async def test_user_location(user: str, US: bool):
#     """Test user location policy based on US or non-US settings."""
#     global US_ip, SE_ip, ip_to_location_base_url
#     # Update user location based on the provided country flag
#     if US:
#         publish_data_user_location(f"{ip_to_location_base_url}{US_ip}", user)
#         print(f"{user}'s location set to: US. Expected outcome: NOT ALLOWED.")
#     else:
#         publish_data_user_location(f"{ip_to_location_base_url}{SE_ip}", user)
#         print(f"{user}'s location set to: SE. Expected outcome: ALLOWED.")

#     # Allow time for the policy engine to process the update
#     await asyncio.sleep(1)

#     # Test authorization after updating the location
#     if await test_authorization(user) == US:
#         return True

# async def test_data(iterations, user, current_country):
#     """Run the user location policy tests multiple times."""

#     for ip, country in zip(ips, countries):

#         publish_data_user_location(f"{ip_to_location_base_url}{ip}", user)

#         if (current_country == country):
#             print(f"{user}'s location set to: {country}. current_country is set to: {current_country} Expected outcome: ALLOWED.")
#         else:
#             print(f"{user}'s location set to: {country}. current_country is set to: {current_country} Expected outcome: NOT ALLOWED.")

#         await asyncio.sleep(1)

#         if await test_authorization(user) == (not (current_country == country)):
#             return True


# def update_policy(country_value):
#     """Update the policy file dynamically."""

#     global policy_file_path, second_script_path

#     global gitea_password, gitea_user_name, gitea_repo_url, temp_dir, branches

#     # Command arguments to update the policy
#     print()
#     print()
#     print(branches)
#     print()
#     print()
#     args = [
#         "python",  # Python executable
#         second_script_path,  # Script path
#         "--user_name",
#         gitea_user_name,
#         "--password",
#         gitea_password,
#         "--gitea_repo_url",
#         gitea_repo_url,
#         "--temp_dir",
#         temp_dir,
#         "--branches",
#         branches,
#         "--file_name", 
#         policy_file_path,
#         "--file_content",
#         (
#             "package app.rbac\n"
#             "default allow = false\n\n"
#             "# Allow the action if the user is granted permission to perform the action.\n"
#             "allow {\n"
#             "\t# unless user location is outside US\n"
#             "\tcountry := data.users[input.user].location.country\n"
#             "\tcountry == \"" + country_value + "\"\n"
#             "}"
#         ),
#     ]

#     # Execute the external script to update the policy
#     subprocess.run(args)

#     # Allow time for the update to propagate
#     import time
#     for i in range(20, 0, -1):
#         print(f"waiting for OPAL server to pull the new policy {i} secondes left", end='\r') 
#         time.sleep(1)

# async def main(iterations):
#     """
#     Main function to run tests with different policy settings.
    
#     This script updates policy configurations and tests access 
#     based on specified settings and locations. It integrates 
#     with Gitea and OPA for policy management and testing.
#     """
#     global gitea_password, gitea_user_name, gitea_repo_url, temp_dir, branches, ips, countries, policy_file_path, OPA_base_url, policy_URI
#     global policy_url, current_directory, second_script_path, CLIENT_TOKEN, DATASOURCE_TOKEN

#     # Parse command-line arguments
#     parser = argparse.ArgumentParser(description="Script to test policy updates using Gitea and OPA.")
#     #parser.add_argument("--file_name", type=str, required=True, help="Name of the file to be processed.")
#     #parser.add_argument("--file_content", type=str, required=True, help="Content of the file to be written or updated.")

#     parser.add_argument("--gitea_password", type=str, required=True, help="Password for the Gitea account.")
#     parser.add_argument("--gitea_user_name", type=str, required=True, help="Username for the Gitea account.")
#     parser.add_argument("--gitea_repo_url", type=str, required=True, help="URL of the Gitea repository to manage.")
#     parser.add_argument("--temp_dir", type=str, required=True, help="Temporary directory for storing tokens and files.")
#     parser.add_argument("--branches", nargs="+", type=str, required=True, help="List of branches to be processed in the Gitea repository.")

#     parser.add_argument("--locations", nargs="+", type=str, required=True, help="List of IP-country pairs (e.g., '192.168.1.1,US').")
#     parser.add_argument("--OPA_base_url", type=str, required=False, default="http://localhost:8181/", help="Base URL for the OPA API.")
#     parser.add_argument("--policy_URI", type=str, required=False, default="v1/data/app/rbac/allow", help="Policy URI to manage RBAC rules in OPA.")

#     args = parser.parse_args()

#     # Assign parsed arguments to global variables
#     gitea_password = args.gitea_password
#     gitea_user_name = args.gitea_user_name
#     gitea_repo_url = args.gitea_repo_url
#     temp_dir = args.temp_dir
#     branches = " ".join(args.branches)



#     # Parse locations into separate lists of IPs and countries
#     ips = []
#     countries = []
#     for location in args.locations:
#         ips.append(location.split(',')[0])
#         countries.append(location.split(',')[1])

#     policy_file_path = "rbac.rego"  # Path to the policy file

#     # OPA and policy settings
#     OPA_base_url = args.OPA_base_url
#     policy_URI = args.policy_URI
#     policy_url = f"{OPA_base_url}{policy_URI}"

#     # Get the directory of the current script
#     current_directory = os.path.dirname(os.path.abspath(__file__))

#     # Path to the external script for policy updates
#     second_script_path = os.path.join(current_directory, "gitea_branch_update.py")

#     # Read tokens from files
#     with open(os.path.join(temp_dir, "OPAL_CLIENT_TOKEN.tkn"), 'r') as client_token_file:
#         CLIENT_TOKEN = client_token_file.read().strip()
#     with open(os.path.join(temp_dir, "OPAL_DATASOURCE_TOKEN.tkn"), 'r') as datasource_token_file:
#         DATASOURCE_TOKEN = datasource_token_file.read().strip()

#     # Update policy to allow only non-US users
#     print("Updating policy to allow only users from SE (Sweden)...")
#     update_policy("SE")

#     if await test_data(iterations,"bob", "SE"):
#         return True

#     print("Policy updated to allow only US users. Re-running tests...")

#     # Update policy to allow only US users
#     update_policy("US")

#     if await test_data(iterations,"bob", "US"):
#         return True

# # Run the asyncio event loop
# if __name__ == "__main__":
#     _error = asyncio.run(main(3))

#     if _error:
#         print("Finished testing: NOT SUCCESSFUL.")
#     else:
#         print("Finished testing: SUCCESSFUL.")
