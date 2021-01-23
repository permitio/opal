# Authorizon sidecar
The sidecar syncs with the authorization service and maintains up-to-date policy cache for open policy agent.

## Running locally (during development)
```
uvicorn horizon.main:app --reload --port=7000
```

you can pass environment variables to control the behavior of the sidecar:
e.g, running a local sidecar against production backend:
```
AUTHZ_SERVICE_URL=https://api.authorizon.com CLIENT_TOKEN=<CLIENT_TOKEN> uvicorn horizon.main:app --reload --port=7000
```

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

## Building the docker image yourself
```
READ_ONLY_GITHUB_TOKEN=<GITHUB_TOKEN> make build
```
you must declare the environment variable `READ_ONLY_GITHUB_TOKEN` for this command to work.

## Running the image in development mode
```
DEV_MODE_CLIENT_TOKEN=<CLIENT_TOKEN> make run
```
you must declare the environment variable `DEV_MODE_CLIENT_TOKEN` for this command to work.