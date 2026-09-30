FROM python:3.13-slim

# Cloud Run demo image. Cloud Run's managed front end is the only ingress, so its
# forwarded headers are trusted: Uvicorn then sees HTTPS, which the secure cookies
# and same-origin checks need. The passwordless admin shortcut is local-only and
# switched off here; set PARALLAX_ADMIN_PASSWORD at deploy time (docs/deployment.md).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FORWARDED_ALLOW_IPS=* \
    PARALLAX_SECURE_COOKIES=1 \
    PARALLAX_DEMO_ADMIN=0 \
    PARALLAX_DEMO_CONTROLS=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py knowledge.py model.py ./
COPY trackrecord/ ./trackrecord/
COPY static/ ./static/
COPY data/sources.json ./data/sources.json
COPY docs/evaluation.json ./docs/evaluation.json

RUN useradd --uid 10001 --create-home parallax \
    && chown -R parallax:parallax /app
USER parallax

EXPOSE 8080
CMD ["sh", "-c", "exec python -m uvicorn app:app --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers"]
