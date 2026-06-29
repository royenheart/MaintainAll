FROM soulter/astrbot:latest

# Pre-install astrbot_plugin_hermes_connector (cloned at build time, not tracked in git).
# Connects AstrBot to the Hermes Hub for remote agent control.
RUN git clone --depth 1 \
    https://github.com/konodiodaaaaa1/astrbot_plugin_hermes_connector \
    /AstrBot/data/plugins/astrbot_plugin_hermes_connector && \
    rm -rf /AstrBot/data/plugins/astrbot_plugin_hermes_connector/.git && \
    pip install --no-cache-dir -r /AstrBot/data/plugins/astrbot_plugin_hermes_connector/requirements.txt
