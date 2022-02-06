FROM permitio/opal-server:latest
RUN pip install --no-cache-dir --user broadcaster[kafka]