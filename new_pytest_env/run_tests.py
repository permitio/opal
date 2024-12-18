import os
import subprocess
import time
import argparse
import sys

def run_script(script_name):
    """
    Runs a Python script from the same folder as this script.

    :param script_name: Name of the Python script to run (e.g., 'script.py').
    """
    current_folder = os.path.dirname(os.path.abspath(__file__))
    script_path = os.path.join(current_folder, script_name)

    if not os.path.exists(script_path):
        print(f"Error: The script '{script_name}' does not exist in the current folder.")
        sys.exit(1)

    try:
        subprocess.run(["python", script_path], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error: An error occurred while running the script '{script_name}': {e}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Run deployment and testing scripts.")
    parser.add_argument("--deploy", action="store_true", help="Include deployment steps before testing.")
    args = parser.parse_args()

    if args.deploy:
        print("Starting deployment...")
        run_script("gitea_docker_py.py")
        time.sleep(10)

        run_script("github_clone_to_gitea.py")
        time.sleep(10)

        run_script("opal_docker_py.py")
        time.sleep(20)

    print("Starting testing...")
    run_script("test.py")

if __name__ == "__main__":
    main()
