FROM python:3.12-slim

# Install app dependencies (not hermes-agent deps — those come from volume)
COPY requirements.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements.txt

WORKDIR /app
COPY hermes_api.py .

# hermes-agent source will be mounted at runtime
ENV HERMES_SRC=/opt/hermes-agent
ENV PYTHONPATH="${HERMES_SRC}:${PYTHONPATH}"
ENV HERMES_HOME=/home/hermes/.hermes

RUN mkdir -p /home/hermes/.hermes

EXPOSE 8420

CMD ["python", "hermes_api.py"]
