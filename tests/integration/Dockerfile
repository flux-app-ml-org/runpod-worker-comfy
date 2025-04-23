FROM python:3.9-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    git \
    curl \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Install MinIO Client (mc)
RUN wget https://dl.min.io/client/mc/release/linux-amd64/mc -O /usr/local/bin/mc && \
    chmod +x /usr/local/bin/mc

# Clone ComfyUI repository
RUN git clone https://github.com/comfyanonymous/ComfyUI.git /comfyui

# Install ComfyUI dependencies
WORKDIR /comfyui
RUN pip install --no-cache-dir -r requirements.txt

# Go back to app directory
WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt /app/requirements.txt
COPY tests/integration/requirements.txt /app/tests/integration/requirements.txt

# Install both project and test dependencies
RUN pip install --no-cache-dir -r /app/requirements.txt && \
    pip install --no-cache-dir -r /app/tests/integration/requirements.txt && \
    pip install --no-cache-dir minio

# Copy project files
COPY src /app/src
COPY tests /app/tests

# Set environment variables
ENV PYTHONPATH=/app
ENV COMFY_OUTPUT_PATH=/comfyui/output
ENV COMFY_HOST=127.0.0.1:8188
ENV COMFY_POLLING_INTERVAL_MS=100
ENV COMFY_POLLING_MAX_RETRIES=100
ENV PYTHONUNBUFFERED=1
ENV FLASK_DEBUG=1
ENV WORKFLOW_FILE=/app/workflow.json
ENV RESULT_IMAGE_WEBHOOK_URL=http://mock-webhook:8189/webhook
ENV RESULT_IMAGE_WEBHOOK_SECRET=test-webhook-secret
ENV BUCKET_ENDPOINT_URL=http://minio:9000
ENV BUCKET_ACCESS_KEY_ID=minioadmin
ENV BUCKET_SECRET_ACCESS_KEY=minioadmin
ENV S3_REGION=us-east-1
ENV S3_BUCKET_NAME=runpod-images
# ENV =/app/tests/integration/data/webhook

# Create necessary directories
RUN mkdir -p /comfyui/output /app/tests/integration/data/comfy /app/tests/integration/data/s3

# Set working directory for tests
WORKDIR /app/tests/integration