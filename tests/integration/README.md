# Integration Tests for RunPod ComfyUI Worker

This directory contains integration tests for the RunPod ComfyUI worker.

## Overview

These tests validate the end-to-end functionality of the RunPod worker for ComfyUI, including:

1. Image generation workflows
2. Webhook notifications of completed images
3. S3 upload functionality (mocked)
4. Image handling and processing

## Test Architecture

The test setup consists of three services:

1. **Integration Test Runner**: Runs the actual tests against the handler
2. **Mock ComfyUI Server**: Simulates the ComfyUI backend for testing without requiring the full ComfyUI installation
3. **Mock Webhook Server**: Receives and validates webhook notifications about completed images

## Running the Tests

To run the integration tests, simply execute the script:

```bash
./run_docker_tests.sh
```

This will:
1. Build the Docker containers
2. Start the mock services
3. Run the integration tests
4. Stop the containers when done

## Viewing Results

After running the tests, you can check the following for results:

- `data/comfy/`: Contains data related to ComfyUI state

## Adding More Tests

To add more tests:

1. Extend the `TestHandlerIntegration` class in `test_integration.py`
2. Create new test methods that start with `test_`
3. Update `mock_comfyui.py` if you need to simulate different ComfyUI behaviors
4. Update `mock_webhook_server.py` if you need to test different webhook functionalities

## Environment Variables

The tests use several environment variables to configure behavior:

- `COMFY_HOST`: Address of the ComfyUI server
- `RESULT_IMAGE_WEBHOOK_URL`: URL to send webhook notifications
- `RESULT_IMAGE_WEBHOOK_SECRET`: Secret key for webhook authentication
- `BUCKET_ENDPOINT_URL`: Mock S3 bucket endpoint URL
