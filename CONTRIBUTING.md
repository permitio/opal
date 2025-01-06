# Contributing Guide

We would love for you to contribute to this project and help make it even better than it is today! 💎

As a contributor, here are the guidelines we would like you to follow:
 - [Code of Conduct](https://github.com/permitio/opal/blob/master/CODE_OF_CONDUCT.md)
 - [Question or Problem?](#question)
 - [Issues and Bugs](#issue)
 - [Feature Requests](#feature)
 - [Development Guidelines](#development)

## <a name="question"></a> Got a Question or Problem?
Come talk to us about OPAL, or authorization in general - we would love to hear from you ❤️

You can:
- Raise questions in our [GitHub discussions](https://github.com/permitio/opal/discussions)
- Report issues and ask for features in [GitHub issues](https://github.com/permitio/opal/issues)
- Follow us on [Twitter](https://twitter.com/opal_ac) to get the latest OPAL updates
- Join our [Slack community](https://io.permit.io/slack) to chat about authorization, open-source, realtime communication, tech or anything else! We are super available on Slack ;)

If you are using our project, please consider giving us a ⭐️
</br>
</br>

[![Join our Slack](https://i.ibb.co/wzrGHQL/Group-749.png)](https://bit.ly/opal-slack)</br> [![Follow us on Twitter](https://i.ibb.co/k4x55Lr/Group-750.png)](https://twitter.com/opal_ac)

### <a name="issue"></a> Found a Bug?
If you find a bug in the source code, you can help us by [submitting an issue](https://github.com/permitio/opal/issues) or even better, you can [submit a Pull Request](#submit-pr) with a fix.

Before you submit an issue, please search the issue tracker; maybe an issue for your problem already exists, and the discussion might inform you of workarounds readily available.

We want to fix all the issues as soon as possible, but before fixing a bug, we need to reproduce and confirm it.
In order to reproduce bugs, we require that you provide:
- Full logs of OPAL server and OPAL client
- Your configuration for OPAL server and OPAL client
  - i.e.: Docker Compose, Kubernetes YAMLs, environment variables, etc.
  - Redact any secrets/tokens/API keys in your config

### <a name="feature"></a> Missing a Feature?
You can *request* a new feature by [submitting an issue](https://github.com/permitio/opal/issues) to our GitHub Repository.
Please provide as much detail and context as possible, along with examples or references to similar features, as this will help us understand your request better.

We encourage you to contribute to OPAL by submitting a [Pull Request](#submit-pr) with your feature implementation and are happy to guide you through the process.

Custom Fetch Providers are a great way to extend OPAL, and we would love to see your implementation of a new fetch provider!
To get started, you can check out the tutorial on how to [Write Your Own Fetch Provider](https://opal.ac/tutorials/write_your_own_fetch_provider).

We are always looking to improve OPAL and would love to hear your ideas!

### <a name="submit-pr"></a> Submitting a Pull Request (PR)

Pull requests are welcome! 🙏

Please follow these guidelines:

1. **Create an Issue**: Open a [GitHub Issue](https://github.com/permitio/opal/issues) for your feature or bug fix.
2. **Fork & Branch**: Fork this repository and create a new branch based on `master`. Name your branch descriptively (e.g., `fix/issue-123`, `feature/new-fetch-provider`).
3. **Write Tests**: If your changes affect functionality, include tests.
4. **Update Documentation**: Ensure any new features or configurations are documented.
5. **Check Quality**: Run all tests and linters:
    ```bash
    pytest
    pre-commit run --all-files
    ```
6. **Submit PR**: Open a pull request, linking to the issue and explaining your changes clearly.

We aim to review all PRs promptly. After you submit a PR, here’s what you can expect:
1. **Initial Review:** A maintainer will review your PR within a few days. If there are any issues, they will provide feedback.
2. **Feedback:** If changes are needed, please make the necessary updates and push them to your branch. The PR will be updated automatically.
3. **Approval:** Once your PR is approved, it will be merged into the main branch.
4. **Release:** Your changes will be included in the next release of OPAL. We will update the changelog and release notes accordingly.
5. **Announcement:** We will announce your contribution in our community channels and give you a shoutout! 🎉

### Contributor Checklist

Before submitting your contribution, ensure the following:

- [ ] Issue created and linked in the PR
- [ ] Branch created from `master` and appropriately named
- [ ] Tests written and passing
- [ ] Documentation updated (if applicable)
- [ ] Code formatted and linted
- [ ] Changes thoroughly explained in the PR description

## <a name="development"></a> Development Guidelines

We are excited to have you onboard as a contributor to OPAL! 🎉

### Setting up Your Development Environment

#### Prerequisites
- [Python](https://www.python.org/downloads/)
- [Docker](https://docs.docker.com/get-docker/)
- [OPA](https://www.openpolicyagent.org/docs/latest/#running-opa)

1. Fork the repository and clone it to your local machine.
2. Create a virtual environment and install the dependencies:
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    ```
3. Install the pre-commit hooks:
    ```bash
    pre-commit install
    ```

### Running OPAL Servers and Clients

You can run the OPAL server and client locally using the OPAL CLI or using uvicorn directly.
### Configuring OPAL
Configure OPAL by setting environment variables:
```bash
export OPAL_POLICY_REPO_URL=https://github.com/permitio/opal-example-policy-repo
export OPAL_DATA_CONFIG_SOURCES={"config":{"entries":[{"url":"http://localhost:7002/policy-data","topics":["policy_data"],"dst_path":"/static"}]}}
export OPAL_SERVER_URL=http://localhost:7002
```

More information about the available configurations can be found in the [OPAL documentation](https://opal.ac/getting-started/configuration).

#### Using OPAL CLI
```bash
opal-server run
opal-client run
```

#### Using uvicorn
```bash
uvicorn opal_server.main:app --reload
uvicorn opal_client.main:app --reload
```

### Building the Docker Images

You can build the Docker images for the OPAL server and client using the following commands:
```bash
make docker-build-server
make docker-build-client  # with inline OPA engine
make docker-build-client-cedar  # with inline cedar agent engine
make docker-build-client-standalone  # without inline engine
```

### Running the Documentation Locally

When contributing to the documentation, you can run the documentation locally and preview your changes live.

#### Prerequisites
- [Node.js](https://nodejs.org/en/download/)

#### Setting Up
1. Navigate to the `docs` directory:
    ```bash
    cd documentation
    ```
2. Install the dependencies:
    ```bash
    npm install
    ```

#### Running the Documentation Live

You can run the documentation live using the following command:
```bash
npm run start
```

### Linting and Formatting

You can run the linting and formatting checks using the following command:
```bash
pre-commit run --all-files
```

### Running the Tests

You can run the tests using the following command:
```bash
pytest
```

### Running E2E Tests

The E2E tests run OPAL Server and Client in a docker-compose environment and test the core features of OPAL.
They are external to the OPAL packages and are located in the `app-tests` directory.

Read more about how to run the E2E tests in the [app-tests README](app-tests/README.md).

---

We’re excited to see your contributions and will do our best to support you through the process! 👏
