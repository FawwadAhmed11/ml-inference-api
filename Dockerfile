# ============================================
# Stage 1: Builder
# ============================================
FROM python:3.11-slim as builder 

WORKDIR /app

# Install build dependencies

RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user \
    torch torchvision --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir --user -r requirements.txt 


# ============================================
# Stage 2: Runtime
# ============================================
FROM python:3.11-slim
WORKDIR /app

# Create non-root user and /home/appuser/ dir for model download
RUN groupadd -r appuser && \
    useradd -r -g appuser appuser && \
    chown -R appuser:appuser /app && \
    mkdir -p /home/appuser/.cache && \
    chown -R appuser:appuser /home/appuser

# Copy Python packages from builder
COPY --from=builder /root/.local /home/appuser/.local


# Update PATH
ENV PATH=/home/appuser/.local/bin:$PATH \
    PYTHONUNBUFFERED=1

# Copy application code
COPY --chown=appuser:appuser src/model-serve/app.py src/model-serve/config.py src/model-serve/middleware.py src/model-serve/log_config.py ./

# Switch to non-root user
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health')" || exit 1

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
