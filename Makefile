.PHONY: help

.DEFAULT_GOAL := help

help:
	@echo "Available commands:"
	@echo "  docs-dev              - Start the documentation site in development mode"
	@echo "  clean                 - Clean Python package build artifacts"
	@echo "  build-packages        - Build Python packages"
	@echo "  publish               - Clean, build, and publish packages to PyPI"
	@echo "  install-client-from-src - Install opal-client from source"
	@echo "  install-server-from-src - Install opal-server from source"
	@echo "  install-develop       - Install development dependencies"
	@echo "  docker-build-client   - Build opal-client Docker image"
	@echo "  docker-build-server   - Build opal-server Docker image"
	@echo "  docker-run-client     - Run opal-client in Docker"
	@echo "  docker-run-server     - Run opal-server in Docker"
	@echo "  docker-build-client-eopa - Build opal-client-eopa Docker image"
	@echo "  e2e-test              - Run E2E tests"
	@echo "  e2e-test-verbose      - Run E2E tests with verbose output"
	@echo "  e2e-test-clean        - Clean up E2E test environment"

OPAL_SERVER_URL ?= http://host.docker.internal:7002
OPAL_AUTH_PRIVATE_KEY ?= /root/ssh/opal_rsa
OPAL_AUTH_PUBLIC_KEY ?= /root/ssh/opal_rsa.pub
OPAL_POLICY_STORE_URL ?= http://host.docker.internal:8181

# python packages (pypi)
clean:
	cd packages/opal-common/ ; rm -rf *.egg-info build/ dist/
	cd packages/opal-client/ ; rm -rf *.egg-info build/ dist/
	cd packages/opal-server/ ; rm -rf *.egg-info build/ dist/

build-packages:
	cd packages/opal-common/ ; python setup.py sdist bdist_wheel
	cd packages/opal-client/ ; python setup.py sdist bdist_wheel
	cd packages/opal-server/ ; python setup.py sdist bdist_wheel

publish-to-pypi:
	cd packages/opal-common/ ; python -m twine upload dist/*
	cd packages/opal-client/ ; python -m twine upload dist/*
	cd packages/opal-server/ ; python -m twine upload dist/*

publish:
	$(MAKE) clean
	$(MAKE) build-packages
	$(MAKE) publish-to-pypi

install-client-from-src:
	pip install packages/opal-client

install-server-from-src:
	pip install packages/opal-server

install-develop:
	pip install -r requirements.txt

# docs
docs-dev:
	@cd documentation && yarn start

# docker
docker-build-client:
	@docker build -t permitio/opal-client --target client -f docker/Dockerfile .

docker-build-client-eopa:
	@docker build -t permitio/opal-client-eopa --target client-eopa -f docker/Dockerfile .

docker-build-client-cedar:
	@docker build -t permitio/opal-client-cedar --target client-cedar -f docker/Dockerfile .

docker-build-client-standalone:
	@docker build -t permitio/opal-client-standalone --target client-standalone -f docker/Dockerfile .

docker-run-client:
	@docker run -it -e "OPAL_SERVER_URL=$(OPAL_SERVER_URL)" -p 7766:7000 -p 8181:8181 permitio/opal-client

docker-run-client-standalone:
	@docker run -it \
		-e "OPAL_SERVER_URL=$(OPAL_SERVER_URL)" \
		-e "OPAL_POLICY_STORE_URL=$(OPAL_POLICY_STORE_URL)" \
		-p 7766:7000 \
		permitio/opal-client-standalone

docker-build-server:
	@docker build -t permitio/opal-server --target server -f docker/Dockerfile .

docker-build-next:
	@docker build -t permitio/opal-client-standalone:next --target client-standalone -f docker/Dockerfile .
	@docker build -t permitio/opal-client:next --target client -f docker/Dockerfile .
	@docker build -t permitio/opal-server:next --target server -f docker/Dockerfile .
	@docker build -t permitio/opal-client-eopa:next --target client-eopa -f docker/Dockerfile .

docker-build-latest:
	@docker build -t permitio/opal-client-standalone:latest --target client-standalone -f docker/Dockerfile .
	@docker build -t permitio/opal-client:latest --target client -f docker/Dockerfile .
	@docker build -t permitio/opal-server:latest --target server -f docker/Dockerfile .
	@docker build -t permitio/opal-client-eopa:latest --target client-eopa -f docker/Dockerfile .

docker-build-alpine:
	@docker build -t permitio/opal-client:latest-alpine --target client-alpine -f docker/Dockerfile .
	@docker build -t permitio/opal-server:latest-alpine --target server-alpine -f docker/Dockerfile .

docker-build-client-alpine:
	@docker build -t permitio/opal-client:next-alpine --target client-alpine -f docker/Dockerfile .

docker-build-client-standalone-alpine:
	@docker build -t permitio/opal-client-standalone:next-alpine --target client-standalone-alpine -f docker/Dockerfile .

docker-build-client-cedar-alpine:
	@docker build -t permitio/opal-client-cedar:next-alpine --target client-cedar-alpine -f docker/Dockerfile .

docker-build-client-next-alpine:
	@docker build -t permitio/opal-client-standalone:next-alpine --target client-standalone-alpine -f docker/Dockerfile .
	@docker build -t permitio/opal-client:next-alpine --target client-alpine -f docker/Dockerfile .
	@docker build -t permitio/opal-client-cedar:next-alpine --target client-cedar-alpine -f docker/Dockerfile .

docker-build-client-latest-alpine:
	@docker build -t permitio/opal-client-standalone:latest-alpine --target client-standalone-alpine -f docker/Dockerfile .
	@docker build -t permitio/opal-client:latest-alpine --target client-alpine -f docker/Dockerfile .
	@docker build -t permitio/opal-client-cedar:latest-alpine --target client-cedar-alpine -f docker/Dockerfile .

docker-build-server-next-alpine:
	@docker build -t permitio/opal-server:next-alpine --target server-alpine -f docker/Dockerfile .

docker-build-server-latest-alpine:
	@docker build -t permitio/opal-server:latest-alpine --target server-alpine -f docker/Dockerfile .

docker-run-server:
	@if [[ -z "$(OPAL_POLICY_REPO_SSH_KEY)" ]]; then \
		docker run -it \
			-e "OPAL_POLICY_REPO_URL=$(OPAL_POLICY_REPO_URL)" \
			-p 7002:7002 \
			permitio/opal-server; \
	else \
		docker run -it \
			-e "OPAL_POLICY_REPO_URL=$(OPAL_POLICY_REPO_URL)" \
			-e "OPAL_POLICY_REPO_SSH_KEY=$(OPAL_POLICY_REPO_SSH_KEY)" \
			-p 7002:7002 \
			permitio/opal-server; \
	fi

docker-run-server-secure:
	@docker run -it \
		-v ~/.ssh:/root/ssh \
		-e "OPAL_AUTH_PRIVATE_KEY=$(OPAL_AUTH_PRIVATE_KEY)" \
		-e "OPAL_AUTH_PUBLIC_KEY=$(OPAL_AUTH_PUBLIC_KEY)" \
		-e "OPAL_POLICY_REPO_URL=$(OPAL_POLICY_REPO_URL)" \
		-p 7002:7002 \
		permitio/opal-server

# E2E tests
.PHONY: e2e-test
e2e-test:
	@echo "Running E2E tests..."
	@cd tests/e2e && pytest -v --tb=short --log-cli-level=INFO

.PHONY: e2e-test-verbose
e2e-test-verbose:
	@echo "Running E2E tests with verbose output..."
	@cd tests/e2e && pytest -vv --tb=long --log-cli-level=DEBUG --capture=no

.PHONY: e2e-test-clean
e2e-test-clean:
	@echo "Cleaning up E2E test environment..."
	@docker compose -f tests/e2e/docker_compose.yml -p opal-e2e-tests down -v

.PHONY: e2e-test-reset
e2e-test-reset: e2e-test-clean e2e-test
	@echo "E2E tests completed with clean environment"
