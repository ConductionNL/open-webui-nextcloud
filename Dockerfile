# Open WebUI Nextcloud ExApp
# Combines Open WebUI chat interface with AppAPI lifecycle management

FROM ghcr.io/open-webui/open-webui:main

# Install additional dependencies for AppAPI wrapper
USER root

RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies (Open WebUI already has Python)
COPY requirements.txt /app/exapp_requirements.txt
RUN pip install --no-cache-dir -r /app/exapp_requirements.txt

# Install FRP client for HaRP support
RUN set -ex; \
    ARCH=$(uname -m); \
    if [ "$ARCH" = "aarch64" ]; then \
      FRP_URL="https://raw.githubusercontent.com/nextcloud/HaRP/main/exapps_dev/frp_0.61.1_linux_arm64.tar.gz"; \
      FRP_DIR="frp_0.61.1_linux_arm64"; \
    else \
      FRP_URL="https://raw.githubusercontent.com/nextcloud/HaRP/main/exapps_dev/frp_0.61.1_linux_amd64.tar.gz"; \
      FRP_DIR="frp_0.61.1_linux_amd64"; \
    fi; \
    curl -L "$FRP_URL" -o /tmp/frp.tar.gz; \
    tar -C /tmp -xzf /tmp/frp.tar.gz; \
    cp /tmp/${FRP_DIR}/frpc /usr/local/bin/frpc; \
    chmod +x /usr/local/bin/frpc; \
    rm -rf /tmp/frp* /tmp/${FRP_DIR}

# Copy ExApp wrapper
COPY ex_app /app/ex_app

# Create data directory
RUN mkdir -p /data

WORKDIR /app

# Expose ports
EXPOSE 9000 8080

# Environment defaults
ENV APP_HOST=0.0.0.0
ENV APP_PORT=9000
ENV PYTHONUNBUFFERED=1
ENV WEBUI_AUTH=true
ENV ENABLE_SIGNUP=false

# Entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
