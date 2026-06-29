FROM python:3.12-slim

# Install app dependencies
COPY ./server/hermes-api/requirements.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Install cuactl dependency (httpx) and create cuactl CLI
RUN pip install --no-cache-dir httpx>=0.28.0

WORKDIR /app
COPY ./server/hermes-api/hermes_api.py .

# Copy cuactl relay server (CLI tool called by hermes-agent)
COPY ./server/cua-relay/relay_server.py /usr/local/bin/relay_server.py
RUN echo '#!/bin/sh\nexec python3 /usr/local/bin/relay_server.py "$@"' > /usr/local/bin/cuactl && chmod +x /usr/local/bin/cuactl

# hermes-agent source will be mounted at runtime
ENV HERMES_SRC=/opt/hermes-agent
ENV PYTHONPATH="${HERMES_SRC}:${PYTHONPATH}"
ENV HERMES_HOME=/home/hermes/.hermes

RUN mkdir -p /home/hermes/.hermes

EXPOSE 8420

CMD ["python", "hermes_api.py"]
