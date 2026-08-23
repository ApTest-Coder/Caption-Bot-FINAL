FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

# Install runtime dependencies only; pytest/ruff stay out of the image.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# `.dockerignore` keeps .env, local databases and the git history out of the
# image, so credentials are supplied at run time (`--env-file .env`) instead of
# being baked into a layer.
COPY . .

# Run as an unprivileged user. The data directory is created and handed over
# before the drop so SQLite deployments can still write to it.
RUN mkdir -p data \
    && useradd --create-home --uid 10001 botuser \
    && chown -R botuser:botuser /app
USER botuser

CMD ["python", "main.py"]
