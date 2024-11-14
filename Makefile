.PHONY: help

.DEFAULT_GOAL := help

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

# docker
docker-build-client:
	@docker build -t permitio/opal-client --target client -f docker/Dockerfile .

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
