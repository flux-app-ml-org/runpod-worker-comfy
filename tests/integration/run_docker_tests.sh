#!/bin/bash
set -e

# Change to the integration test directory
cd "$(dirname "$0")"

# Print test files info
echo "Test data directory contents:"
ls -la data/

# Build and run the Docker container
echo "Building and running Docker container for integration tests..."
docker compose build
docker compose run --rm integration-tests

# Cleanup
echo "Cleaning up..."
docker compose down

echo "Tests completed."