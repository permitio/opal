.PHONY: help

.DEFAULT_GOAL := help

# DOCKER TASKS
# Build the container
build: ## Build the container
	docker build -t authorizon/sidecar --build-arg READ_ONLY_GITHUB_TOKEN=$(READ_ONLY_GITHUB_TOKEN) .

run: ## Run the container
	docker run -it -e "AUTHZ_SERVICE_URL=http://host.docker.internal:8000" -e "CLIENT_TOKEN=$(DEV_MODE_CLIENT_TOKEN)" -p 7000:7000 authorizon/sidecar
