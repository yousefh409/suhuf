# recitation/Dockerfile
# Production container for the recitation server.
# Targets a CUDA image; for CPU-only deploys, change the base image.
FROM nvidia/cuda:12.3.1-runtime-ubuntu22.04

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 python3-pip ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Model weights expected at /app/models/ssl_xls_r_v5/.
# Bake them in by COPYing during build, or mount at runtime.

EXPOSE 8000
CMD ["python3", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
