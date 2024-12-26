# import argparse
# import requests
# from git import Repo
# import os
# import shutil


# # Replace these with your Gitea server details and personal access token
# gitea_base_url = ""  # Replace with your Gitea server URL

# repo_name = ""
# source_rbac_file = ""
# clone_directory = ""
# private = ""
# description = ""

# temp_dir = ""

# data_dir = ""

# user_name = ""  # Your Gitea username

# access_token = ""


# def repo_exists(repo_name):
#     url = f"{gitea_base_url}/repos/{user_name}/{repo_name}"
#     headers = {"Authorization": f"token {access_token}"}
#     response = requests.get(url, headers=headers)
#     if response.status_code == 200:
#         print(f"Repository '{repo_name}' already exists.")
#         return True
#     elif response.status_code == 404:
#         return False
#     else:
#         print(f"Failed to check repository: {response.status_code} {response.text}")
#         response.raise_for_status()


# def create_gitea_repo(repo_name, description="", private=False, auto_init=True, default_branch="master"):
#     url = f"{gitea_base_url}/user/repos"
#     headers = {
#         "Authorization": f"token {access_token}",
#         "Content-Type": "application/json"
#     }
#     payload = {
#         "name": repo_name,
#         "description": description,
#         "private": private,
#         "auto_init": auto_init,
#         "default_branch": default_branch  # Set the default branch
#     }
#     response = requests.post(url, json=payload, headers=headers)
#     if response.status_code == 201:
#         print("Repository created successfully!")
#         return response.json()
#     else:
#         print(f"Failed to create repository: {response.status_code} {response.text}")
#         response.raise_for_status()

# def clone_repo_with_gitpython(repo_name, clone_directory):
#     repo_url = f"http://localhost:3000/{user_name}/{repo_name}.git"
#     if access_token:
#         repo_url = f"http://{user_name}:{access_token}@localhost:3000/{user_name}/{repo_name}.git"
#     try:
#         if os.path.exists(clone_directory):
#             print(f"Directory '{clone_directory}' already exists. Deleting it...")
#             shutil.rmtree(clone_directory)
#         Repo.clone_from(repo_url, clone_directory)
#         print(f"Repository '{repo_name}' cloned successfully into '{clone_directory}'.")
#     except Exception as e:
#         print(f"Failed to clone repository '{repo_name}': {e}")

# def get_default_branch(repo):
#     try:
#         # Fetch the default branch name
#         return repo.git.symbolic_ref("refs/remotes/origin/HEAD").split("/")[-1]
#     except Exception as e:
#         print(f"Error determining default branch: {e}")
#         return None

# def reset_repo_with_rbac(repo_directory, source_rbac_file):
#     try:
#         if not os.path.exists(repo_directory):
#             raise FileNotFoundError(f"Repository directory '{repo_directory}' does not exist.")

#         git_dir = os.path.join(repo_directory, ".git")
#         if not os.path.exists(git_dir):
#             raise FileNotFoundError(f"The directory '{repo_directory}' is not a valid Git repository (missing .git folder).")

#         repo = Repo(repo_directory)

#         # Get the default branch name
#         default_branch = get_default_branch(repo)
#         if not default_branch:
#             raise ValueError("Could not determine the default branch name.")

#         # Ensure we are on the default branch
#         if repo.active_branch.name != default_branch:
#             repo.git.checkout(default_branch)

#         # Remove other branches
#         branches = [branch.name for branch in repo.branches if branch.name != default_branch]
#         for branch in branches:
#             repo.git.branch("-D", branch)

#         # Reset repository content
#         for item in os.listdir(repo_directory):
#             item_path = os.path.join(repo_directory, item)
#             if os.path.basename(item_path) == ".git":
#                 continue
#             if os.path.isfile(item_path) or os.path.islink(item_path):
#                 os.unlink(item_path)
#             elif os.path.isdir(item_path):
#                 shutil.rmtree(item_path)

#         # Copy RBAC file
#         destination_rbac_path = os.path.join(repo_directory, "rbac.rego")
#         shutil.copy2(source_rbac_file, destination_rbac_path)

#         # Stage and commit changes
#         repo.git.add(all=True)
#         repo.index.commit("Reset repository to only include 'rbac.rego'")

#         print(f"Repository reset successfully. 'rbac.rego' is the only file and changes are committed.")
#     except Exception as e:
#         print(f"Error resetting repository: {e}")


# def push_repo_to_remote(repo_directory):
#     try:
#         repo = Repo(repo_directory)

#         # Get the default branch name
#         default_branch = get_default_branch(repo)
#         if not default_branch:
#             raise ValueError("Could not determine the default branch name.")

#         # Ensure we are on the default branch
#         if repo.active_branch.name != default_branch:
#             repo.git.checkout(default_branch)

#         if "origin" not in [remote.name for remote in repo.remotes]:
#             raise ValueError("No remote named 'origin' found in the repository.")

#         # Push changes to the default branch
#         repo.remotes.origin.push(refspec=f"{default_branch}:{default_branch}")
#         print("Changes pushed to remote repository successfully.")
#     except Exception as e:
#         print(f"Error pushing changes to remote: {e}")


# def cleanup_local_repo(repo_directory):
#     """
#     Remove the local repository directory.

#     :param repo_directory: Directory of the cloned repository
#     """
#     try:
#         if os.path.exists(repo_directory):
#             shutil.rmtree(repo_directory)
#             print(f"Local repository '{repo_directory}' has been cleaned up.")
#         else:
#             print(f"Local repository '{repo_directory}' does not exist. No cleanup needed.")
#     except Exception as e:
#         print(f"Error during cleanup: {e}")


# def main():
#     global repo_name, source_rbac_file, clone_directory, private, description, gitea_base_url, user_name, temp_dir, access_token, data_dir

#     parser = argparse.ArgumentParser(description="Setup Gitea with admin user and persistent volume.")
#     parser.add_argument("--temp_dir", required=True, help="Path to the temporary directory.")
#     parser.add_argument("--data_dir", required=True, help="Path to the data directory.")
#     parser.add_argument("--repo_name", required=True, help="repo name.")
#     parser.add_argument("--gitea_base_url", required=True, help="gitea base url.")
#     parser.add_argument("--user_name", required=True, help="user name.")
#     args = parser.parse_args()

#     # Example usage
#     repo_name = args.repo_name
#     gitea_base_url = args.gitea_base_url
#     user_name = args.user_name

#     temp_dir = args.temp_dir
#     data_dir = args.data_dir

#     source_rbac_file = os.path.join(data_dir, "rbac.rego")
#     clone_directory = os.path.join(temp_dir, "test-repo")
#     private = False
#     description = "This is a test repository created via API."

#     with open(os.path.join(temp_dir, "gitea_access_token.tkn")) as gitea_access_token_file:
#         access_token = gitea_access_token_file.read().strip()  # Read and strip token
#     try:
#         if not repo_exists(repo_name):
#             create_gitea_repo(repo_name, description, private)
#         clone_repo_with_gitpython(repo_name, clone_directory)
#         reset_repo_with_rbac(clone_directory, source_rbac_file)
#         push_repo_to_remote(clone_directory)
#         cleanup_local_repo(clone_directory)
#     except Exception as e:
#         print("Error:", e)


# if __name__ == "__main__":
#     main()
