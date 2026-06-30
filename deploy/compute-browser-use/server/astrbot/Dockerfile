FROM soulter/astrbot:latest

ARG HERMES_ACCESS_TOKEN=

# ── Hermes Connector Plugin ──────────────────────────────────────────
# Pre-install + configure for Hub mode (talks to hermes-api container).
RUN git clone --depth 1 \
    https://github.com/konodiodaaaaa1/astrbot_plugin_hermes_connector \
    /AstrBot/data/plugins/astrbot_plugin_hermes_connector && \
    rm -rf /AstrBot/data/plugins/astrbot_plugin_hermes_connector/.git && \
    pip install --no-cache-dir -r /AstrBot/data/plugins/astrbot_plugin_hermes_connector/requirements.txt

COPY ./server/astrbot/patch_hermes_config.py /tmp/
RUN python3 /tmp/patch_hermes_config.py && rm /tmp/patch_hermes_config.py

# ── HAPI Connector Plugin ───────────────────────────────────────────
# Connects AstrBot to coding agents (Codex / Claude Code / Gemini).
RUN git clone --depth 1 \
    https://github.com/LiJinHao999/astrbot_plugin_hapi_connector \
    /AstrBot/data/plugins/astrbot_plugin_hapi_connector && \
    rm -rf /AstrBot/data/plugins/astrbot_plugin_hapi_connector/.git && \
    pip install --no-cache-dir -r /AstrBot/data/plugins/astrbot_plugin_hapi_connector/requirements.txt

COPY ./server/astrbot/patch_hapi_config.py /tmp/
RUN python3 /tmp/patch_hapi_config.py && rm /tmp/patch_hapi_config.py
