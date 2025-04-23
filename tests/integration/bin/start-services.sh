#!/bin/bash
# Start-up script for integration tests environment

echo "Starting services for integration tests..."

# Initialize MinIO first and create the bucket
echo "Initializing MinIO..."
./bin/init-minio.sh

# Start ComfyUI in the background
echo "Starting ComfyUI in background..."
cd /comfyui
python main.py --listen 0.0.0.0 --cpu > /comfyui/comfyui.log 2>&1 &
COMFY_PID=$!

# Wait for ComfyUI to be ready
echo "Waiting for ComfyUI to initialize..."
MAX_RETRIES=30
COUNT=0
while ! curl -s http://127.0.0.1:8188/ > /dev/null; do
  if [ $COUNT -eq $MAX_RETRIES ]; then
    echo "ComfyUI failed to start after $MAX_RETRIES attempts"
    exit 1
  fi
  echo "ComfyUI not ready yet, waiting... (Attempt $COUNT of $MAX_RETRIES)"
  sleep 2
  COUNT=$((COUNT+1))
done

echo "ComfyUI is ready!"

# Update COMFY_HOST environment variable to point to the local ComfyUI
export COMFY_HOST="127.0.0.1:8188"
echo "Set COMFY_HOST=$COMFY_HOST"

# Return to the integration tests directory
cd /app/tests/integration

# Run the integration tests
echo "Running integration tests..."
python -u test_integration.py

# Capture the exit code from the tests
TEST_EXIT_CODE=$?

# Stop ComfyUI
echo "Stopping ComfyUI (PID: $COMFY_PID)..."
kill $COMFY_PID

# Exit with the same code as the tests
exit $TEST_EXIT_CODE
