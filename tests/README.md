# tests

The tests folder contains integration and unit tests for OPAL. The tests are structured as follows:

- `tests/containers`: a collection of configurations and setups for containerized environments used in testing OPAL, including Docker and Kubernetes configurations.
- `tests/data-fetchers`: a collection of OPAL data fetchers that are used in the tests to fetch data from various sources, such as PostgreSQL, MongoDB, etc.
- `tests/docker`: a collection of Dockerfiles and other Docker-related files used to build Docker images for the tests.
- `tests/policies`: a collection of policies in REGO that are used in the tests to verify that OPAL functions correctly.
- `tests/policy_repos`: this directory implements providers that manage policy repositories using different platforms such as Gitea, GitHub, GitLab, and more. Any additional repository platform that is supported should implement a class derived from `PolicyRepoBase` (e.g., Bitbucket, etc.).
- `tests/app-tests`: a set of integration tests that run OPAL with a sample service and verify that the service is configured correctly.
- `tests/policy_stores`: a collection of tests setup code that verifies the support of policy decision engines such as OPA, Cedar, OpenFGA, etc.-
- `conftest.py`: a set of fixtures that are used across multiple tests to create a consistent test environment.

The tests use the [Pytest](https://pytest.org/en/latest/) testing framework. Additionally, the tests rely on the [testcontainers](https://testcontainers.org/) library to build and run Docker images.

## Infrastructure of the testing system

## Settings

The `settings.py` file contains a class `TestSettings` that one can use to configure global settings for running the tests. The class includes properties for the test environment, such as the location of the test data, the Docker network to use, and more.

## Utilities

The `utils.py` file contains a class `Utils` that one can use to simplify the process of writing tests. The class includes properties and methods for common tasks such as creating temporary directories, copying files, and more.

## Examples of how to build tests

When you write your own test, you will have opal_servers as a list of the opal servers available, and opal_clients as a list of the opal clients available. just include them in your test function as parameters and they will be available to you.


## Running the tests

To run the tests, execute the `run.sh` shell script in the root directory of the repository. This script sets up the environment and runs the tests.


## OPAL API Reference
https://opal-v2.permit.io/redoc#tag/Bundle-Server/operation/get_policy_policy_get
