import os

ALLOWED_ORIGINS = ["*"]

POLICY_REPO_MAIN_BRANCH = os.environ.get("POLICY_REPO_MAIN_BRANCH", "master")
POLICY_REPO_MAIN_REMOTE = os.environ.get("POLICY_REPO_MAIN_REMOTE", "origin")