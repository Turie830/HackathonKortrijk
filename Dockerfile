FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    TRACKRECORD_SECURE_COOKIES=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY trackrecord ./trackrecord
COPY static ./static
COPY docs ./docs
RUN useradd --create-home --uid 10001 app && mkdir -p data && chown app:app data
USER app
EXPOSE 8080
# Set TRACKRECORD_ALLOWED_HOSTS to your host name and TRACKRECORD_DEMO_PASSWORD at deploy time.
CMD ["sh", "-c", "uvicorn trackrecord.web:app --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers --forwarded-allow-ips='*'"]
