# Use an official Python base image
FROM python:3.11-slim

# Set the working directory in the container
# Copy the entire repository into the container
COPY . /workspace
WORKDIR /workspace

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt /workspace/
RUN pip install --no-cache-dir -r /workspace/requirements.txt

# Copy the rest of the repository into the container
COPY . /workspace

# Set the default command for the container
CMD ["/bin/bash"]