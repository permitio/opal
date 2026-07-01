FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir requests==2.32.3 GitPython==3.1.50
COPY seed_gitea.py /seed_gitea.py
ENTRYPOINT ["python", "/seed_gitea.py"]
