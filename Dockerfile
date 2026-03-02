# Open WebUI + Ollama Nextcloud ExApp
# Combined chat interface with built-in LLM inference

# Stage 1: Get Ollama binary
FROM ollama/ollama:latest AS ollama-source

# Stage 2: Build on Open WebUI base
FROM ghcr.io/open-webui/open-webui:main

USER root

# Copy Ollama binary from first stage
COPY --from=ollama-source /bin/ollama /usr/local/bin/ollama

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

# Install Python dependencies for AppAPI wrapper
# (Open WebUI already has Python + pip)
COPY requirements.txt /app/exapp_requirements.txt
RUN pip install --no-cache-dir -r /app/exapp_requirements.txt

# Copy ExApp wrapper and assets
COPY ex_app/ /app/ex_app/
COPY img/ /app/ex_app/img/
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Create data directory
RUN mkdir -p /data

WORKDIR /app

# Ollama data directory
VOLUME /data

# Environment defaults
ENV APP_HOST=0.0.0.0
ENV APP_PORT=23000
ENV PYTHONUNBUFFERED=1
ENV WEBUI_AUTH=true
ENV ENABLE_SIGNUP=false

ENTRYPOINT ["./entrypoint.sh"]
