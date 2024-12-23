from git import Repo, GitCommandError
import shutil
import os
import argparse
import codecs


# Configuration
temp_dir = None

USER_NAME = None
GITEA_REPO_URL = None
PASSWORD = None
CLONE_DIR = None
BRANCHES = None
COMMIT_MESSAGE = None

# Append credentials to the repository URL
authenticated_url = None

# Prepare the directory
def prepare_directory(path):
    """Prepare the directory by cleaning up any existing content."""
    if os.path.exists(path):
        shutil.rmtree(path)  # Remove existing directory
    os.makedirs(path)  # Create a new directory

# Clone and push changes
def clone_and_update(branch, file_name, file_content):
    """Clone the repository, update the specified branch, and push changes."""
    prepare_directory(CLONE_DIR)  # Clean up and prepare the directory
    print(f"Processing branch: {branch}")

    # Clone the repository for the specified branch
    print(f"Cloning branch {branch}...")
    repo = Repo.clone_from(authenticated_url, CLONE_DIR, branch=branch)

    # Create or update the specified file with the provided content
    file_path = os.path.join(CLONE_DIR, file_name)
    with open(file_path, "w") as f:
        f.write(file_content)

    # Stage the changes
    print(f"Staging changes for branch {branch}...")
    repo.git.add(A=True)  # Add all changes

    # Commit the changes if there are modifications
    if repo.is_dirty():
        print(f"Committing changes for branch {branch}...")
        repo.index.commit(COMMIT_MESSAGE)

    # Push changes to the remote repository
    print(f"Pushing changes for branch {branch}...")
    try:
        repo.git.push(authenticated_url, branch)
    except GitCommandError as e:
        print(f"Error pushing branch {branch}: {e}")

# Cleanup function
def cleanup():
    """Remove the temporary clone directory."""
    if os.path.exists(CLONE_DIR):
        print("Cleaning up temporary directory...")
        shutil.rmtree(CLONE_DIR)


def main():

    global temp_dir, USER_NAME, GITEA_REPO_URL, PASSWORD, CLONE_DIR, BRANCHES, COMMIT_MESSAGE, authenticated_url
    
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Clone, update, and push changes to Gitea branches.")
    parser.add_argument("--file_name", type=str, required=True, help="The name of the file to create or update.")
    parser.add_argument("--file_content", type=str, required=True, help="The content of the file to create or update.")
    
    parser.add_argument("--user_name", type=str, required=True)
    parser.add_argument("--password", type=str, required=True)
    parser.add_argument("--gitea_repo_url", type=str, required=True)
    parser.add_argument("--temp_dir", type=str, required=True)
    parser.add_argument("--branches", nargs='+', type=str, required=True)

    args = parser.parse_args()

    file_name = args.file_name
    
    temp_dir = args.temp_dir

    # Decode escape sequences in the file content
    file_content = codecs.decode(args.file_content, 'unicode_escape')



    GITEA_REPO_URL = args.gitea_repo_url #"http://localhost:3000/{USER_NAME}/opal-example-policy-repo.git"  # Replace with your Gitea repository URL
    USER_NAME = args.user_name #"permitAdmin"                   # Replace with your Gitea username
    PASSWORD = args.password #"Aa123456"                       # Replace with your Gitea password (or personal access token)
    
    BRANCHES = args.branches #["master"]                       # List of branches to handle
    
    CLONE_DIR = os.path.join(temp_dir, "branch_update")                           # Local directory to clone the repo into

    COMMIT_MESSAGE = "Automated update commit"  # Commit message


    # Append credentials to the repository URL
    authenticated_url = GITEA_REPO_URL.replace("http://", f"http://{USER_NAME}:{PASSWORD}@")


    try:
        # Process each branch in the list
        for branch in BRANCHES:
            clone_and_update(branch, file_name, file_content)
        print("Operation completed successfully.")
    finally:
        # Ensure cleanup is performed regardless of success or failure
        cleanup()
    
# Main entry point
if __name__ == "__main__":
    main()