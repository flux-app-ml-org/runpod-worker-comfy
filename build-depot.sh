LATEST_COMMIT_SHA=$(git rev-parse HEAD)
depot build --push . -t fajyz/runpod-worker-comfy:${LATEST_COMMIT_SHA} --platform linux/amd64 --target=final \
  --build-arg HUGGINGFACE_ACCESS_TOKEN="${HUGGINGFACE_ACCESS_TOKEN}"