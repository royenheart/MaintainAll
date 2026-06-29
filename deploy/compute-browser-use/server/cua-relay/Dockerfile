FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY relay_server.py setup.py .
RUN pip install -e .

# The cuactl CLI is now available in the container
# It connects to the Client Control Plane via CUACTL_ENDPOINT

CMD ["python", "-c", "import asyncio; asyncio.run(__import__('relay_server')._main())"]
