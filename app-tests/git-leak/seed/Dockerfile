# The same digest-pinned wolfi-base as docker/Dockerfile.
FROM cgr.dev/chainguard/wolfi-base:latest@sha256:8509ee4351a2e501b7f98201f2e2642396e82020c61a589cacdcfe74b9de46c1
RUN apk add --no-cache python-3.14 git && python3.14 -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
RUN pip install --no-cache-dir requests==2.34.2 GitPython==3.2.1
COPY seed_gitea.py /seed_gitea.py
ENTRYPOINT ["python", "/seed_gitea.py"]
