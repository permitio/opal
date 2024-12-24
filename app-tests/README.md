# OPAL Application Tests

To fully test OPAL's core features as part of our CI flow,
We're using a bash script and a docker-compose configuration that enables most of OPAL's important features.

## How To Run Locally

### Controlling the image tag

By default, tests would run with the `latest` image tag (for both server & client).

To configure another specific version:

```bash
export OPAL_IMAGE_TAG=0.7.1
```

Or if you want to test locally built images
```bash
make docker-build-next
export OPAL_IMAGE_TAG=next
```

### Using a policy repo

To test opal's git tracking capabilities, `run.sh` uses a dedicated GitHub repo ([opal-tests-policy-repo](https://github.com/permitio/opal-tests-policy-repo)) in which it creates branches and pushes new commits.

If you're not accessible to that repo (not in `Permit.io`), Please fork our public [opal-example-policy-repo](https://github.com/permitio/opal-example-policy-repo), and override the repo URL to be used:
```bash
export OPAL_POLICY_REPO_URL=git@github.com:your-org/your-repo.git
```

As `run.sh` requires push permissions, and as `opal-server` itself might need to authenticate GitHub (if your repo is private). If your GitHub ssh private key is not stored at `~/.ssh/id_rsa`, provide it using:
```bash
# Use an absolute path
export OPAL_POLICY_REPO_SSH_KEY_PATH=$(realpath ./your_github_ssh_private_key)
```


### Putting it all together

```bash
make docker-build-next # To locally build opal images
export OPAL_IMAGE_TAG=next # Otherwise would default to "latest"

export OPAL_POLICY_REPO_URL=git@github.com:your-org/your-repo.git # To use your own repo for testing (if you're not an Permit.io employee yet...)
export OPAL_POLICY_REPO_SSH_KEY_PATH=$(realpath ./your_github_ssh_private_key) # If your GitHub ssh key isn't in "~.ssh/id_rsa"

cd app-tests
./run.sh
```
