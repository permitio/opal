.PHONY: help

.DEFAULT_GOAL := help

OPAL_SERVER_URL ?= http://host.docker.internal:7002
OPAL_AUTH_PRIVATE_KEY ?= /root/ssh/opal_rsa
OPAL_AUTH_PUBLIC_KEY ?= /root/ssh/opal_rsa.pub
OPAL_POLICY_STORE_URL ?= http://host.docker.internal:8181/v1

# python packages (pypi)
clean:
	rm -rf *.egg-info build/ dist/

build-common:
	$(MAKE) clean
	python setup/setup_common.py sdist bdist_wheel
	mv dist dist-common

build-client:
	$(MAKE) clean
	python setup/setup_client.py sdist bdist_wheel
	mv dist dist-client

build-server:
	$(MAKE) clean
	python setup/setup_server.py sdist bdist_wheel
	mv dist dist-server


publish-common:
	python -m twine upload --repository pypi dist-common/*

publish-client:
	python -m twine upload --repository pypi dist-client/*

publish-server:
	python -m twine upload --repository pypi dist-server/*

# Split the build and publish to ensure all packegs has been built before uploading to PyPI
build:
	# build
	$(MAKE) build-common
	$(MAKE) build-client
	$(MAKE) build-server

publish:
	# build
	$(MAKE) build
	# Publish
	$(MAKE) publish-common
	$(MAKE) publish-client
	$(MAKE) publish-server

install-client-from-src:
	python setup/setup_client.py install

install-server-from-src:
	python setup/setup_server.py install

# docker
docker-build-client:
	@docker build -t authorizon/opal-client --target client -f docker/Dockerfile .

docker-build-client-standalone:
	@docker build -t authorizon/opal-client-standalone --target client-standalone -f docker/Dockerfile .

docker-run-client:
	@docker run -it -e "OPAL_SERVER_URL=$(OPAL_SERVER_URL)" -p 7000:7000 -p 8181:8181 authorizon/opal-client

docker-run-client-standalone:
	@docker run -it \
		-e "OPAL_SERVER_URL=$(OPAL_SERVER_URL)" \
		-e "OPAL_POLICY_STORE_URL=$(OPAL_POLICY_STORE_URL)" \
		-p 7000:7000 \
		authorizon/opal-client-standalone

docker-build-server:
	@docker build -t authorizon/opal-server --target server -f docker/Dockerfile .

docker-run-server:
	@if [[ -z "$(OPAL_POLICY_REPO_SSH_KEY)" ]]; then \
		docker run -it \
			-e "OPAL_POLICY_REPO_URL=$(OPAL_POLICY_REPO_URL)" \
			-p 7002:7002 \
			authorizon/opal-server; \
	else \
		docker run -it \
			-e "OPAL_POLICY_REPO_URL=$(OPAL_POLICY_REPO_URL)" \
			-e "OPAL_POLICY_REPO_SSH_KEY=$(OPAL_POLICY_REPO_SSH_KEY)" \
			-p 7002:7002 \
			authorizon/opal-server; \
	fi

docker-run-server-secure:
	@docker run -it \
		-v ~/.ssh:/root/ssh \
		-e "OPAL_AUTH_PRIVATE_KEY=$(OPAL_AUTH_PRIVATE_KEY)" \
		-e "OPAL_AUTH_PUBLIC_KEY=$(OPAL_AUTH_PUBLIC_KEY)" \
		-e "OPAL_POLICY_REPO_URL=$(OPAL_POLICY_REPO_URL)" \
		-p 7002:7002 \
		authorizon/opal-server
