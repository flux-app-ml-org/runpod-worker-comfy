import unittest
import os
import sys
import json
import time
import threading
import requests

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from src.rp_handler import handler
from mock_webhook_server import app as webhook_app, received_webhooks

os.makedirs('data/comfy', exist_ok=True)
os.makedirs('data/s3', exist_ok=True)
comfy_output_path = os.path.join('/comfyui/output')

class TestHandlerIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Start mock webhook server in a separate thread
        cls.webhook_thread = threading.Thread(target=lambda: webhook_app.run(host='127.0.0.1', port=8189, debug=False, use_reloader=False))
        cls.webhook_thread.daemon = True
        cls.webhook_thread.start()

        # Give servers time to start
        time.sleep(2)

        # Check if servers are running
        try:
            comfy_response = requests.get('http://127.0.0.1:8188/')
            webhook_response = requests.get('http://127.0.0.1:8189/')
            print(f"ComfyUI server status: {comfy_response.status_code}")
            print(f"Webhook server status: {webhook_response.status_code}")
        except Exception as e:
            print(f"Error checking server status: {str(e)}")
        
    def setUp(self):
        # Clear any previous webhook data
        received_webhooks.clear()
        
        # Ensure the comfy data directory exists
        os.makedirs('data/comfy', exist_ok=True)
        # Remove any previous workflow.json file
        workflow_file = os.path.join('data/comfy', 'workflow.json')
        if os.path.exists(workflow_file):
            os.remove(workflow_file)
        for file in os.listdir(comfy_output_path):
            os.remove(os.path.join(comfy_output_path, file))

    def test_basic_workflow_with_webhook(self):
        """Test basic workflow execution with webhook notification"""
        # Set environment variables for testing
        os.environ['RESULT_IMAGE_WEBHOOK_URL'] = 'http://127.0.0.1:8189/webhook'
        os.environ['RESULT_IMAGE_WEBHOOK_SECRET'] = 'test-webhook-secret'
        os.environ['TEST_DATA_DIR'] = 'data/comfy'
        
        # Load the sample workflow that just saves 3 images
        workflow = json.loads(open('data/workflow.json').read())
        
        # Test with a sample image
        job_input = {
            "workflow": [workflow],
            "inferenceJobId": "test-inference-job",
        }

        # Create a mock job structure
        job = {
            "id": "test-job-id",
            "input": job_input
        }

        # Call the handler
        print("Calling handler with test job input...")
        response = handler(job)
        print(f"Handler response: {response}")

        # Check if the response contains expected keys
        self.assertIn("refresh_worker", response)
        self.assertIn("result", response)
        result = response["result"]

        self.assertTrue(isinstance(result, list))
        for item in result:
            self.assertTrue(isinstance(item, dict), f"Item should be a dictionary: {item}")
            self.assertIn("status", item, "Status should be in the item")
            self.assertEqual(item["status"], "success", "Status should be success")
            self.assertIn("message", item, "Message should be in the item")
            self.assertTrue(item["message"].startswith("http://minio:9000/runpod-images/test-job-id/"), "Message should start with http://minio:9000/runpod-images/test-job-id/")
        
        print(f"Webhook received {len(received_webhooks)} webhooks")
        print(f"Received webhooks: {received_webhooks}")
        for idx, item in enumerate(received_webhooks):
            for key in ['job_id', 'image_url', 'image_name', 'inferenceJobId']:
                self.assertIn(key, item, f"{key} should be in the item")
            self.assertEqual(item["job_id"], "test-job-id", "Job id should be test-job-id")
            self.assertEqual(item["image_url"], result[idx]["message"], f"Image url should be {result[idx]['message']}")
            self.assertTrue(item["image_name"].endswith(".png"), f"Image name should end with .png: {item['image_name']}")
            self.assertEqual(item["inferenceJobId"], "test-inference-job", "Inference job id should be test-inference-job")
        
        # Verify that the workflow was properly sent to ComfyUI
        # If images exist, the workflow was executed and 3 images were saved
        for path in ['test_1__00001_.png', 'test_2__00001_.png', 'test_3__00001_.png']:
            self.assertTrue(os.path.exists(os.path.join(comfy_output_path, path)), "Image file was not saved by ComfyUI")
        
if __name__ == '__main__':
    unittest.main()
