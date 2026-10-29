FROM python:3.11-slim AS builder
WORKDIR /build
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN python -m pip install --no-cache-dir build \
    && python -m build --wheel --outdir /wheels

FROM python:3.11-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATABASE_URL=sqlite:////app/data/students.sqlite \
    ENVIRONMENT=production \
    LOG_LEVEL=INFO
WORKDIR /app
COPY --from=builder /wheels/*.whl /wheels/
RUN python -m pip install --no-cache-dir /wheels/*.whl \
    && rm -rf /wheels \
    && groupadd --gid 10001 appuser \
    && useradd --uid 10001 --gid appuser --create-home appuser \
    && mkdir -p /app/data \
    && chown appuser:appuser /app/data
USER appuser
VOLUME ["/app/data"]
EXPOSE 8000
STOPSIGNAL SIGTERM
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import json, urllib.request; response = urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2); assert response.status == 200; assert json.load(response)['status'] == 'ok'"
CMD ["python", "-m", "uvicorn", "student_manager.api:app", "--host", "0.0.0.0", "--port", "8000"]
