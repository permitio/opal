# Use an OpenResty base image
FROM openresty/openresty:alpine-fat

# Install dependencies
RUN apk update && apk add --no-cache python3 py3-pip && \
    python3 -m venv /venv && \
    . /venv/bin/activate && \
    pip install --upgrade pip && \
    pip install flask && \
    pip install requests && \
    pip install jwt

RUN apk add --no-cache shadow

RUN addgroup -S nginx && adduser -S nginx -G nginx

# Set up the Python environment and install other dependencies
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN . /venv/bin/activate && pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . /app

# Copy NGINX configuration to OpenResty’s NGINX path
COPY nginx.conf /usr/local/openresty/nginx/conf/nginx.conf

# Set environment variables for Flask
ENV FLASK_APP=app.py

# Expose necessary ports
EXPOSE 80 5000

# Ensure the log directory and log file exist, and set proper permissions
RUN mkdir -p /var/log/nginx && \
    touch /var/log/nginx/proxy_access.log && \
    chown nginx:nginx /var/log/nginx/proxy_access.log && \
    touch /var/log/nginx/error.log && \
    chown nginx:nginx /var/log/nginx/error.log

# Run both OpenResty and Flask
COPY start.sh /start.sh
RUN chmod +x /start.sh
CMD /start.sh