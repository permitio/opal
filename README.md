# Authorizon sidecar
The sidecar syncs with the authorization service and maintains up-to-date policy cache for open policy agent.

## Installing and running in production

Pull the image from docker hub
```
docker pull authorizon/sidecar
```

Run the image (by default exposes port 7000 but you can change it):
```
docker run -it -p 7000:7000 authorizon/sidecar
```

3. alternatively, run the image via another service: AWS ECS, EKS, kubernetes, etc.

## Building the docker image yourself
```
docker build . -t authorizon/sidecar
```