import unittest
from unittest.mock import patch, MagicMock, mock_open, Mock
import sys
import os
import json
import base64
import hmac
import hashlib

# Make sure that "src" is known and can be used to import rp_handler.py
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))
from src import rp_handler

# Local folder for test resources
RUNPOD_WORKER_COMFY_TEST_RESOURCES_IMAGES = "./test_resources/images"


class TestRunpodWorkerComfy(unittest.TestCase):
    def test_valid_input_with_workflow_only(self):
        input_data = {"workflow": {"key": "value"}}
        validated_data, error = rp_handler.validate_input(input_data)
        self.assertIsNone(error)
        self.assertEqual(validated_data, {"workflow": {"key": "value"}, "images": None})

    def test_valid_input_with_workflow_and_images(self):
        input_data = {
            "workflow": {"key": "value"},
            "images": [{"name": "image1.png", "image": "base64string"}],
        }
        validated_data, error = rp_handler.validate_input(input_data)
        self.assertIsNone(error)
        self.assertEqual(validated_data, input_data)

    def test_input_missing_workflow(self):
        input_data = {"images": [{"name": "image1.png", "image": "base64string"}]}
        validated_data, error = rp_handler.validate_input(input_data)
        self.assertIsNotNone(error)
        self.assertEqual(error, "Missing 'workflow' parameter")

    def test_input_with_invalid_images_structure(self):
        input_data = {
            "workflow": {"key": "value"},
            "images": [{"name": "image1.png"}],  # Missing 'image' key
        }
        validated_data, error = rp_handler.validate_input(input_data)
        self.assertIsNotNone(error)
        self.assertEqual(
            error, "'images' must be a list of objects with 'name' and 'image' keys"
        )

    def test_invalid_json_string_input(self):
        input_data = "invalid json"
        validated_data, error = rp_handler.validate_input(input_data)
        self.assertIsNotNone(error)
        self.assertEqual(error, "Invalid JSON format in input")

    def test_valid_json_string_input(self):
        input_data = '{"workflow": {"key": "value"}}'
        validated_data, error = rp_handler.validate_input(input_data)
        self.assertIsNone(error)
        self.assertEqual(validated_data, {"workflow": {"key": "value"}, "images": None})

    def test_empty_input(self):
        input_data = None
        validated_data, error = rp_handler.validate_input(input_data)
        self.assertIsNotNone(error)
        self.assertEqual(error, "Please provide input")

    @patch("rp_handler.requests.get")
    def test_check_server_server_up(self, mock_requests):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_requests.return_value = mock_response

        result = rp_handler.check_server("http://127.0.0.1:8188", 1, 50)
        self.assertTrue(result)

    @patch("rp_handler.requests.get")
    def test_check_server_server_down(self, mock_requests):
        mock_requests.get.side_effect = rp_handler.requests.RequestException()
        result = rp_handler.check_server("http://127.0.0.1:8188", 1, 50)
        self.assertFalse(result)

    @patch("rp_handler.urllib.request.urlopen")
    def test_queue_prompt(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"prompt_id": "123"}).encode()
        mock_urlopen.return_value = mock_response
        result = rp_handler.queue_workflow({"prompt": "test"})
        self.assertEqual(result, {"prompt_id": "123"})

    @patch("rp_handler.urllib.request.urlopen")
    def test_get_history(self, mock_urlopen):
        # Mock response data as a JSON string
        mock_response_data = json.dumps({"key": "value"}).encode("utf-8")

        # Define a mock response function for `read`
        def mock_read():
            return mock_response_data

        # Create a mock response object
        mock_response = Mock()
        mock_response.read = mock_read

        # Mock the __enter__ and __exit__ methods to support the context manager
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = Mock()

        # Set the return value of the urlopen mock
        mock_urlopen.return_value = mock_response

        # Call the function under test
        result = rp_handler.get_history("123")

        # Assertions
        self.assertEqual(result, {"key": "value"})
        mock_urlopen.assert_called_with("http://127.0.0.1:8188/history/123")

    @patch("builtins.open", new_callable=mock_open, read_data=b"test")
    def test_base64_encode(self, mock_file):
        test_data = base64.b64encode(b"test").decode("utf-8")

        result = rp_handler.base64_encode("dummy_path")

        self.assertEqual(result, test_data)

    @patch("rp_handler.os.path.exists")
    @patch("src.rp_handler.base64_encode")
    @patch.dict(
        os.environ, {"COMFY_OUTPUT_PATH": RUNPOD_WORKER_COMFY_TEST_RESOURCES_IMAGES}
    )
    def test_bucket_endpoint_not_configured(self, mock_base64_encode, mock_exists):
        mock_exists.return_value = True
        mock_base64_encode.return_value = "base64_encoded_image_data"

        outputs = {
            "node_id": {"images": [{"filename": "ComfyUI_00001_.png", "subfolder": ""}]}
        }
        job_id = "123"

        result = rp_handler.process_output_images(outputs, job_id)

        # Check the first item in the result list
        self.assertTrue(isinstance(result, list))
        self.assertEqual(result[0]["status"], "success")
        self.assertEqual(result[0]["message"], "base64_encoded_image_data")
        mock_base64_encode.assert_called_once_with(f"{RUNPOD_WORKER_COMFY_TEST_RESOURCES_IMAGES}/ComfyUI_00001_.png")

    @patch("rp_handler.os.path.exists")
    @patch("rp_handler.rp_upload.files")
    @patch.dict(
        os.environ,
        {
            "COMFY_OUTPUT_PATH": RUNPOD_WORKER_COMFY_TEST_RESOURCES_IMAGES,
            "BUCKET_ENDPOINT_URL": "http://example.com",
        },
    )
    def test_bucket_endpoint_configured(self, mock_files, mock_exists):
        # Mock the os.path.exists to return True, simulating that the image exists
        mock_exists.return_value = True

        # Mock the rp_upload.files to return a simulated URL list
        mock_files.return_value = ["http://example.com/uploaded/image.png"]

        # Define the outputs and job_id for the test
        outputs = {"node_id": {"images": [{"filename": "ComfyUI_00001_.png", "subfolder": "test"}]}}
        job_id = "123"

        # Call the function under test
        result = rp_handler.process_output_images(outputs, job_id)

        # Assertions
        self.assertTrue(isinstance(result, list))
        self.assertEqual(result[0]["status"], "success")
        self.assertEqual(result[0]["message"], "http://example.com/uploaded/image.png")
        mock_files.assert_called_once_with(
            job_id, ["./test_resources/images/test/ComfyUI_00001_.png"]
        )

    @patch("rp_handler.os.path.exists")
    @patch("rp_handler.rp_upload.files")
    @patch.dict(
        os.environ,
        {
            "COMFY_OUTPUT_PATH": RUNPOD_WORKER_COMFY_TEST_RESOURCES_IMAGES,
            "BUCKET_ENDPOINT_URL": "http://example.com",
            "BUCKET_ACCESS_KEY_ID": "",
            "BUCKET_SECRET_ACCESS_KEY": "",
        },
    )
    def test_bucket_image_upload_fails_env_vars_wrong_or_missing(
        self, mock_files, mock_exists
    ):
        # Simulate the file existing in the output path
        mock_exists.return_value = True

        # When AWS credentials are wrong or missing, return an empty list
        mock_files.return_value = []

        outputs = {
            "node_id": {"images": [{"filename": "ComfyUI_00001_.png", "subfolder": ""}]}
        }
        job_id = "123"

        result = rp_handler.process_output_images(outputs, job_id)

        # Check that the result is an empty list when no images are uploaded
        self.assertEqual(result, [])

    @patch("src.rp_handler.requests.post")
    def test_upload_images_successful(self, mock_post):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "Successfully uploaded"
        mock_post.return_value = mock_response

        test_image_data = base64.b64encode(b"Test Image Data").decode("utf-8")

        images = [{"name": "test_image.png", "image": test_image_data}]

        response = rp_handler.upload_images(images)

        # Check that the response has the right structure and values
        self.assertEqual(response["status"], "success")
        self.assertEqual(response["message"], "All images uploaded successfully")
        self.assertEqual(len(response["details"]), 1)
        self.assertEqual(response["details"][0], "Successfully uploaded test_image.png")

    @patch("src.rp_handler.requests.post")
    def test_upload_images_failed(self, mock_post):
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = "Error uploading"
        mock_post.return_value = mock_response

        test_image_data = base64.b64encode(b"Test Image Data").decode("utf-8")

        images = [{"name": "test_image.png", "image": test_image_data}]

        response = rp_handler.upload_images(images)

        # Check that the response has the right structure and values
        self.assertEqual(response["status"], "error")
        self.assertEqual(response["message"], "Some images failed to upload")
        self.assertEqual(len(response["details"]), 1)
        self.assertEqual(response["details"][0], "Error uploading test_image.png: Error uploading")

    @patch("src.rp_handler.requests.post")
    @patch("builtins.open", mock_open(read_data=b"test_image_data"))
    @patch.dict(os.environ, {
        "RESULT_IMAGE_WEBHOOK_URL": "http://webhook.example.com",
        "RESULT_IMAGE_WEBHOOK_SECRET": "test_secret"
    })
    def test_send_image_to_webhook_success(self, mock_post):
        # Mock successful webhook response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "Success"
        mock_post.return_value = mock_response

        # Test the webhook function with explicit parameters
        result = rp_handler.send_image_to_webhook(
            "test_image.png", 
            "job123", 
            "http://webhook.example.com", 
            "test_secret"
        )
        
        # Check the result is True
        self.assertTrue(result)
        
        # Verify the mock was called with the correct arguments
        mock_post.assert_called_once()
        
        # Check that the URL used is correct
        self.assertEqual(mock_post.call_args[0][0], "http://webhook.example.com")
        
        # Check that the headers contain the X-Webhook-Signature
        self.assertIn("X-Webhook-Signature", mock_post.call_args[1]["headers"])
        
        # Check that the signature is correct
        expected_payload = {
            "job_id": "job123",
            "image_data": base64.b64encode(b"test_image_data").decode("utf-8"),
            "image_name": "test_image.png"
        }
        expected_payload_json = json.dumps(expected_payload)
        expected_signature = hmac.new(
            "test_secret".encode(),
            expected_payload_json.encode(),
            hashlib.sha256
        ).hexdigest()
        
        self.assertEqual(
            mock_post.call_args[1]["headers"]["X-Webhook-Signature"],
            expected_signature
        )

    @patch("src.rp_handler.requests.post")
    @patch("builtins.open", mock_open(read_data=b"test_image_data"))
    @patch.dict(os.environ, {
        "RESULT_IMAGE_WEBHOOK_URL": "http://webhook.example.com",
        "RESULT_IMAGE_WEBHOOK_SECRET": "test_secret"
    })
    def test_send_image_to_webhook_failure(self, mock_post):
        # Mock failed webhook response
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response

        # Test the webhook function with explicit parameters
        result = rp_handler.send_image_to_webhook(
            "test_image.png", 
            "job123", 
            "http://webhook.example.com", 
            "test_secret"
        )
        
        # Check the result is False
        self.assertFalse(result)
        
        # Verify the mock was called
        mock_post.assert_called_once()

    @patch("src.rp_handler.requests.post")
    @patch("builtins.open", mock_open(read_data=b"test_image_data"))
    @patch.dict(os.environ, {
        "RESULT_IMAGE_WEBHOOK_URL": "http://webhook.example.com",
        "RESULT_IMAGE_WEBHOOK_SECRET": "test_secret"
    })
    def test_send_image_to_webhook_exception(self, mock_post):
        # Mock an exception during webhook call
        mock_post.side_effect = Exception("Network error")

        # Test the webhook function with explicit parameters
        result = rp_handler.send_image_to_webhook(
            "test_image.png", 
            "job123", 
            "http://webhook.example.com", 
            "test_secret"
        )
        
        # Check the result is False
        self.assertFalse(result)
        
        # Verify the mock was called
        mock_post.assert_called_once()

    @patch("src.rp_handler.os.path.exists")
    @patch("src.rp_handler.rp_upload.files")
    @patch("src.rp_handler.send_image_to_webhook")
    @patch.dict(os.environ, {
        "COMFY_OUTPUT_PATH": RUNPOD_WORKER_COMFY_TEST_RESOURCES_IMAGES,
        "BUCKET_ENDPOINT_URL": "http://example.com",
        "RESULT_IMAGE_WEBHOOK_URL": "http://webhook.example.com",
        "RESULT_IMAGE_WEBHOOK_SECRET": "test_secret"
    })
    def test_process_output_images_with_webhook(self, mock_webhook, mock_files, mock_exists):
        # Mock the os.path.exists to return True
        mock_exists.return_value = True
        
        # Mock the webhook call to return True (success)
        mock_webhook.return_value = True
        
        # Mock the S3 upload to return a URL
        mock_files.return_value = ["http://example.com/uploaded/image.png"]

        # Define the outputs and job_id for the test
        outputs = {"node_id": {"images": [{"filename": "ComfyUI_00001_.png", "subfolder": ""}]}}
        job_id = "123"

        # Call the function under test
        result = rp_handler.process_output_images(outputs, job_id)

        # Assertions for normal S3 upload flow
        self.assertTrue(isinstance(result, list))
        self.assertEqual(result[0]["status"], "success")
        self.assertEqual(result[0]["message"], "http://example.com/uploaded/image.png")
        
        # Assert that webhook was called with all four parameters
        mock_webhook.assert_called_once_with(
            f"{RUNPOD_WORKER_COMFY_TEST_RESOURCES_IMAGES}/ComfyUI_00001_.png", 
            "123",
            "http://webhook.example.com",
            "test_secret"
        )

    @patch("src.rp_handler.os.path.exists")
    @patch("src.rp_handler.base64_encode")
    @patch("src.rp_handler.send_image_to_webhook")
    @patch.dict(os.environ, {
        "COMFY_OUTPUT_PATH": RUNPOD_WORKER_COMFY_TEST_RESOURCES_IMAGES,
        "RESULT_IMAGE_WEBHOOK_URL": "http://webhook.example.com",
        "RESULT_IMAGE_WEBHOOK_SECRET": "test_secret"
    })
    def test_process_output_images_with_webhook_no_s3(self, mock_webhook, mock_base64_encode, mock_exists):
        # Mock the os.path.exists to return True
        mock_exists.return_value = True
        
        # Mock the webhook call to return False (failure, but should continue)
        mock_webhook.return_value = False
        
        # Mock the base64 encoding
        mock_base64_encode.return_value = "base64_encoded_image_data"

        # Define the outputs and job_id for the test
        outputs = {"node_id": {"images": [{"filename": "ComfyUI_00001_.png", "subfolder": ""}]}}
        job_id = "123"

        # Call the function under test
        result = rp_handler.process_output_images(outputs, job_id)

        # Assertions for base64 encoding flow
        self.assertTrue(isinstance(result, list))
        self.assertEqual(result[0]["status"], "success")
        self.assertEqual(result[0]["message"], "base64_encoded_image_data")
        
        # Assert that webhook was called with all four parameters
        mock_webhook.assert_called_once_with(
            f"{RUNPOD_WORKER_COMFY_TEST_RESOURCES_IMAGES}/ComfyUI_00001_.png", 
            "123",
            "http://webhook.example.com",
            "test_secret"
        )
        
        # Assert that base64 encoding was still performed
        mock_base64_encode.assert_called_once_with(f"{RUNPOD_WORKER_COMFY_TEST_RESOURCES_IMAGES}/ComfyUI_00001_.png")
