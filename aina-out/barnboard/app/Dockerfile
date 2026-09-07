# Golden starter — FastAPI + HTMX. Deploys to the Hetzner VPS or Fly via Docker.
# (Python apps don't belong on Vercel; this image is the portable unit.)
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PORT=8000
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
# Honor $PORT (VPS/Fly inject it); default 8000.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
