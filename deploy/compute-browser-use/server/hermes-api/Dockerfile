FROM python:3.12-slim

# Git needed to clone the Hermes Hub during build
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && \
    rm -rf /var/lib/apt/lists/*

COPY ./server/hermes-api/requirements.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements.txt

RUN pip install --no-cache-dir httpx>=0.28.0

WORKDIR /app

# Clone Hermes Hub from upstream (external plugin repo, MIT licensed)
# Only the hub/ subdirectory is needed at runtime
RUN git clone --depth 1 --filter=blob:none \
    https://github.com/konodiodaaaaa1/astrbot_plugin_hermes_connector /tmp/plugin && \
    cp -r /tmp/plugin/hub /app/hub && \
    rm -rf /tmp/plugin

# Copy cuactl relay server (CLI tool called by hermes-agent)
COPY ./server/cua-relay/relay_server.py /usr/local/bin/relay_server.py
RUN echo '#!/bin/sh\nexec python3 /usr/local/bin/relay_server.py "$@"' > /usr/local/bin/cuactl && chmod +x /usr/local/bin/cuactl

# Keep old hermes_api.py for fallback use
COPY ./server/hermes-api/hermes_api.py /app/hermes_api_fallback.py

# hermes-agent source will be mounted at runtime
ENV HERMES_SRC=/opt/hermes-agent
ENV PYTHONPATH="${HERMES_SRC}:${PYTHONPATH}"
ENV HERMES_HOME=/home/hermes/.hermes
# Hub env defaults (can be overridden by docker-compose)
ENV HERMES_HOST=0.0.0.0
ENV HERMES_PORT=8420

RUN mkdir -p /home/hermes/.hermes

EXPOSE 8420

CMD ["python", "-m", "hub.main"]
