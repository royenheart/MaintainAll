FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        git ca-certificates curl xz-utils \
    && rm -rf /var/lib/apt/lists/*

COPY ./server/hermes-api/requirements.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements.txt

WORKDIR /app

# ── Hermes Hub (HTTP wrapper, from astrbot_plugin_hermes_connector) ──────
RUN git clone --depth 1 --filter=blob:none \
    https://github.com/konodiodaaaaa1/astrbot_plugin_hermes_connector /tmp/plugin && \
    cp -r /tmp/plugin/hub /app/hub && \
    rm -rf /tmp/plugin

# ── Hermes Agent (official installer) ───────────────────────────────────
# Uses the official install.sh from hermes-agent.nousresearch.com.
# --skip-browser: no Playwright/Chromium (headless server, not needed for Hub).
# --skip-setup:   don't run interactive `hermes setup` wizard.
# Installs to /usr/local/lib/hermes-agent, links hermes to /usr/local/bin/hermes.
# FHS root layout — matches Claude Code / Codex CLI conventions.
RUN curl -fsSL https://hermes-agent.nousresearch.com/install.sh | \
    bash -s -- --skip-browser --skip-setup
ENV HERMES_HOME=/home/hermes/.hermes

# ── cuactl relay ─────────────────────────────────────────────────────────
# cuactl no longer lives in this image. It runs as a separate HTTP
# microservice (see server/cua-relay/Dockerfile.http + the `cuactl`
# service in docker-compose.yml). Hermes Agent reaches it at
# http://cuactl:8000/cuactl/<command> via curl in terminal_tool, driven
# by the system_prompt_append in server/hermes/config.yaml.

# Keep old hermes_api.py for fallback use
COPY ./server/hermes-api/hermes_api.py /app/hermes_api_fallback.py

RUN mkdir -p /home/hermes/.hermes

EXPOSE 8420

# Entrypoint: start the Hub (hermes is already on PATH from installer)
RUN printf '#!/bin/sh\nexec python -m hub.main\n' > /entrypoint.sh && chmod +x /entrypoint.sh
CMD ["/entrypoint.sh"]
