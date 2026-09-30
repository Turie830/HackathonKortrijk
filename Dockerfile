FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py knowledge.py model.py ./
COPY static/ ./static/
COPY data/sources.json ./data/sources.json

RUN useradd --uid 10001 --create-home parallax \
    && chown -R parallax:parallax /app
USER parallax

EXPOSE 8080
CMD ["sh", "-c", "exec python -m uvicorn app:app --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers"]
