# Authorizon sidecar
The sidecar syncs with the authorization service and maintains up-to-date policy cache for open policy agent.

## Installing and running in production

Pull the image from docker hub
```
docker pull authorizon/sidecar
```

Run the image: don't forget to pass your authorization service API KEY:
```
docker run -it -e "CLIENT_TOKEN=<YOUR API KEY>" -p 7000:7000 authorizon/sidecar
```

By default the image exposes port 7000 but you can change it.

3. alternatively, run the image via another service: AWS ECS, EKS, kubernetes, etc.

## Building the docker image yourself
```
make build
```
you must declare the environment variable `READ_ONLY_GITHUB_TOKEN` for this command to work.

## Running the image in development mode
```
make run
```
you must declare the environment variable `DEV_MODE_CLIENT_TOKEN` for this command to work.