FROM python:3.12-slim

WORKDIR /app

# Install deps first so Docker caches this layer separately from code changes
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
