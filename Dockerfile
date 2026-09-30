FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PARALLAX_SECURE_COOKIES=1 PARALLAX_DEMO_ADMIN=0 PARALLAX_DEMO_CONTROLS=0
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py knowledge.py model.py ./
COPY trackrecord ./trackrecord
COPY static ./static
COPY docs/evaluation.json ./docs/evaluation.json
COPY data/sources.json ./data/sources.json
RUN useradd --create-home --uid 10001 app && chown -R app:app /app/data
USER app
EXPOSE 8080
# Set PARALLAX_ALLOWED_HOSTS and PARALLAX_DEMO_PASSWORD at deploy time. Cloud Run's front end is the only
# ingress, so its forwarded headers are trusted for the scheme (secure cookies, same-origin checks).
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers --forwarded-allow-ips='*'"]
