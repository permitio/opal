# The same digest-pinned wolfi-base as docker/Dockerfile.
FROM cgr.dev/chainguard/wolfi-base:latest@sha256:94fa13e26d449f7d78dbcd02d12ea37a0da80d24fcc3e1f17b95d515dec607a7
RUN apk add --no-cache python-3.14 git && python3.14 -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
RUN pip install --no-cache-dir requests==2.34.2 GitPython==3.2.1
COPY seed_gitea.py /seed_gitea.py
ENTRYPOINT ["python", "/seed_gitea.py"]
