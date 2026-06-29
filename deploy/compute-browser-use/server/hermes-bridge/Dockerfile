FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bridge_service.py .

EXPOSE 8421

CMD ["uvicorn", "bridge_service:app", "--host", "0.0.0.0", "--port", "8421"]
