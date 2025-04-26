from typing import Optional, Tuple
import uuid
import boto3.session
import runpod
import json
import urllib.request
import urllib.parse
import time
import os
import requests
import base64
from io import BytesIO
import logging
import sys
import hmac
import hashlib
from loki_logger_handler.loki_logger_handler import LokiLoggerHandler
import boto3
from boto3.s3.transfer import TransferConfig
from botocore.config import Config
import multiprocessing

# Time to wait between API check attempts in milliseconds
COMFY_API_AVAILABLE_INTERVAL_MS = 50
# Maximum number of API check attempts
COMFY_API_AVAILABLE_MAX_RETRIES = 500
# Time to wait between poll attempts in milliseconds
COMFY_POLLING_INTERVAL_MS = int(os.environ.get("COMFY_POLLING_INTERVAL_MS", 250))
# Maximum number of poll attempts
COMFY_POLLING_MAX_RETRIES = int(os.environ.get("COMFY_POLLING_MAX_RETRIES", 500))
# Host where ComfyUI is running
COMFY_HOST = os.environ.get("COMFY_HOST", "127.0.0.1:8188")

# Enforce a clean state after each job is done
# see https://docs.runpod.io/docs/handler-additional-controls#refresh-worker
REFRESH_WORKER = os.environ.get("REFRESH_WORKER", "false").lower() == "true"

BUCKET_ACCESS_KEY_ID = os.environ.get("BUCKET_ACCESS_KEY_ID", None)
BUCKET_SECRET_ACCESS_KEY = os.environ.get("BUCKET_SECRET_ACCESS_KEY", None)
BUCKET_ENDPOINT_URL = os.environ.get("BUCKET_ENDPOINT_URL", False)
S3_REGION = os.environ.get("S3_REGION", None)
S3_BUCKET_NAME = os.environ.get("S3_BUCKET_NAME", None)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

LOKI_URL = os.getenv("LOKI_URL")

if LOKI_URL:
    logger.info("Configuring Loki logging.")
    loki_handler = LokiLoggerHandler(
        url=LOKI_URL,
        labels={"app": "flux-app-inference-serverless-worker"}
    )
    logger.addHandler(loki_handler)
else:
    logger.warning("Loki credentials not provided, falling back to local logging.")
    
    local_handler = logging.StreamHandler(sys.stdout)
    local_handler.setLevel(logging.DEBUG)
    
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    local_handler.setFormatter(formatter)
    
    logger.addHandler(local_handler)
def validate_input(job_input):
    """
    Validates the input for the handler function.

    Args:
        job_input (dict): The input data to validate.

    Returns:
        tuple: A tuple containing the validated data and an error message, if any.
               The structure is (validated_data, error_message).
    """
    # Validate if job_input is provided
    if job_input is None:
        logger.error("Input validation failed", extra={"error": "Please provide input"})
        return None, "Please provide input"

    # Check if input is a string and try to parse it as JSON
    if isinstance(job_input, str):
        try:
            job_input = json.loads(job_input)
        except json.JSONDecodeError:
            logger.error("Input validation failed", extra={"error": "Invalid JSON format in input"})
            return None, "Invalid JSON format in input"

    # Validate 'workflow' in input
    workflow = job_input.get("workflow")
    if workflow is None:
        logger.error("Input validation failed", extra={"error": "Missing 'workflow' parameter"})
        return None, "Missing 'workflow' parameter"

    # Validate 'images' in input, if provided
    images = job_input.get("images")
    if images is not None:
        if not isinstance(images, list) or not all(
            "name" in image and "image" in image for image in images
        ):
            logger.error("Input validation failed", extra={"error": "'images' must be a list of objects with 'name' and 'image' keys"})
            return (
                None,
                "'images' must be a list of objects with 'name' and 'image' keys",
            )

    # Return validated data and no error
    logger.info("Input validation succeeded", extra={"validated_data": {"workflow": workflow, "images": images}})
    return {"workflow": workflow, "images": images}, None


def check_server(url, retries=500, delay=50):
    """
    Check if a server is reachable via HTTP GET request

    Args:
    - url (str): The URL to check
    - retries (int, optional): The number of times to attempt connecting to the server. Default is 50
    - delay (int, optional): The time in milliseconds to wait between retries. Default is 500

    Returns:
    bool: True if the server is reachable within the given number of retries, otherwise False
    """

    for i in range(retries):
        try:
            response = requests.get(url)

            # If the response status code is 200, the server is up and running
            if response.status_code == 200:
                logger.info("API is reachable", extra={"url": url})
                return True
        except requests.RequestException:
            # If an exception occurs, the server may not be ready
            pass

        # Wait for the specified delay before retrying
        time.sleep(delay / 1000)

    logger.error("Failed to connect to server", extra={"url": url, "retries": retries})
    return False


def upload_images(images):
    """
    Upload a list of base64 encoded images to the ComfyUI server using the /upload/image endpoint.

    Args:
        images (list): A list of dictionaries, each containing the 'name' of the image and the 'image' as a base64 encoded string.

    Returns:
        list: A list of responses from the server for each image upload.
    """
    if not images:
        logger.info("No images to upload", extra={})
        return {"status": "success", "message": "No images to upload", "details": []}

    responses = []
    upload_errors = []

    logger.info("Starting image(s) upload", extra={})

    for image in images:
        name = image["name"]
        image_data = image["image"]
        blob = base64.b64decode(image_data)

        # Prepare the form data
        files = {
            "image": (name, BytesIO(blob), "image/png"),
            "overwrite": (None, "true"),
        }

        # POST request to upload the image
        response = requests.post(f"http://{COMFY_HOST}/upload/image", files=files)
        if response.status_code != 200:
            upload_errors.append(f"Error uploading {name}: {response.text}")
            logger.error("Error uploading image", extra={"image_name": name, "error": response.text})
        else:
            responses.append(f"Successfully uploaded {name}")
            logger.info("Successfully uploaded image", extra={"image_name": name})

    if upload_errors:
        logger.error("Image(s) upload completed with errors", extra={"upload_errors": upload_errors})
        return {
            "status": "error",
            "message": "Some images failed to upload",
            "details": upload_errors,
        }

    logger.info("Image(s) upload complete", extra={})
    return {
        "status": "success",
        "message": "All images uploaded successfully",
        "details": responses,
    }


def queue_workflow(workflow):
    """
    Queue a workflow to be processed by ComfyUI

    Args:
        workflow (dict): A dictionary containing the workflow to be processed

    Returns:
        dict: The JSON response from ComfyUI after processing the workflow
    """

    # The top level element "prompt" is required by ComfyUI
    data = json.dumps({"prompt": workflow}).encode("utf-8")

    req = urllib.request.Request(f"http://{COMFY_HOST}/prompt", data=data)
    logger.info("Queuing workflow", extra={"workflow": workflow})
    return json.loads(urllib.request.urlopen(req).read())


def get_history(prompt_id):
    """
    Retrieve the history of a given prompt using its ID

    Args:
        prompt_id (str): The ID of the prompt whose history is to be retrieved

    Returns:
        dict: The history of the prompt, containing all the processing steps and results
    """
    with urllib.request.urlopen(f"http://{COMFY_HOST}/history/{prompt_id}") as response:
        res_json = json.loads(response.read())
        return res_json


def base64_encode(img_path):
    """
    Returns base64 encoded image.

    Args:
        img_path (str): The path to the image

    Returns:
        str: The base64 encoded image
    """
    with open(img_path, "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode("utf-8")
        logger.info("Encoded image to base64", extra={"img_path": img_path})
        return f"{encoded_string}"

def send_url_to_webhook(image_url, job_id, inference_job_id, RESULT_IMAGE_WEBHOOK_URL, RESULT_IMAGE_WEBHOOK_SECRET):
    """
    Sends an image URL to the configured webhook URL with HMAC authentication.
    
    Args:
        image_url (str): The S3 URL of the uploaded image
        job_id (str): The unique job identifier
        inference_job_id (str): The optional inference job identifier
        
    Returns:
        bool: True if the URL was successfully sent, False otherwise
    """ 
    if not inference_job_id:
        logger.warning("No inference job id provided, skipping webhook", extra={})
        return False
    
    try:
        payload = {
            "job_id": job_id,
            "image_url": image_url,
            "image_name": os.path.basename(image_url).split("?")[0],
            "inferenceJobId": inference_job_id
        }
        
        payload_json = json.dumps(payload)
        
        signature = hmac.new(
            RESULT_IMAGE_WEBHOOK_SECRET.encode(),
            payload_json.encode(),
            hashlib.sha256
        ).hexdigest()
        
        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Signature": signature
        }
        
        response = requests.post(
            RESULT_IMAGE_WEBHOOK_URL,
            data=payload_json,
            headers=headers,
            timeout=30
        )
        
        return response.status_code >= 200 and response.status_code < 300
            
    except Exception as e:
        logger.error("Error sending image URL to webhook", extra={"image_url": image_url, "error": str(e)})
        return False


def process_output_images(outputs, job_id, inference_job_id=None):
    """
    This function takes the "outputs" from image generation and the job ID,
    then processes each generated image individually:
    1. Uploads each image to S3 immediately as it's processed
    2. Sends the S3 URL to the webhook for each image
    3. Returns the results for all images

    Args:
        outputs (dict): A dictionary containing the outputs from image generation,
                        typically includes node IDs and their respective output data.
        job_id (str): The unique identifier for the job.
        inference_job_id (str, optional): Optional inference job identifier for webhook.

    Returns:
        dict: A dictionary with the status ('success' or 'error') and the message,
              which is either the URL to the image in the AWS S3 bucket or a base64
              encoded string of the image. In case of error, the message details the issue.
    """

    # The path where ComfyUI stores the generated images
    COMFY_OUTPUT_PATH = os.environ.get("COMFY_OUTPUT_PATH", "/comfyui/output")
    
    RESULT_IMAGE_WEBHOOK_URL = os.environ.get("RESULT_IMAGE_WEBHOOK_URL")
    RESULT_IMAGE_WEBHOOK_SECRET = os.environ.get("RESULT_IMAGE_WEBHOOK_SECRET")
    
    if not RESULT_IMAGE_WEBHOOK_URL or not RESULT_IMAGE_WEBHOOK_SECRET:
        logger.warning("Webhook URL or secret not configured, skipping webhook", extra={})

    output_images = []

    logger.info("Processing output images", extra={"outputs": outputs})

    for node_id, node_output in outputs.items():
        if "images" in node_output:
            for image in node_output["images"]:
                image_path = os.path.join(image["subfolder"], image["filename"])
                output_images.append(image_path)

    logger.info("Image generation is done", extra={})

    results = []

    for image_path in output_images:
        local_image_path = f"{COMFY_OUTPUT_PATH}/{image_path}"
        logger.info("Processing image", extra={"local_image_path": local_image_path})
        
        if not os.path.exists(local_image_path):
            logger.error("The image does not exist in the output folder", extra={"local_image_path": local_image_path})
            results.append({
                "status": "error",
                "message": f"the image does not exist in the specified output folder: {local_image_path}",
            })
            continue

        try:
            # Upload the image to S3 immediately
            image_url = upload_image(job_id, local_image_path)
            
            logger.info("Image uploaded to S3", extra={"image_url": image_url})
            
            # If webhook and inferenceJobId are configured, send URL to webhook immediately
            if RESULT_IMAGE_WEBHOOK_URL and RESULT_IMAGE_WEBHOOK_SECRET and inference_job_id:
                webhook_result = send_url_to_webhook(
                    image_url, 
                    job_id, 
                    inference_job_id, 
                    RESULT_IMAGE_WEBHOOK_URL, 
                    RESULT_IMAGE_WEBHOOK_SECRET
                )
                if webhook_result:
                    logger.info("Image URL sent to webhook successfully", extra={"image_url": image_url})
                else:
                    logger.warning("Failed to send image URL to webhook", extra={"image_url": image_url})
            
            results.append({
                "status": "success",
                "message": image_url,
            })
        except Exception as e:
            logger.error("Failed to upload image to S3", extra={"local_image_path": local_image_path, "error": str(e)})
            logger.debug(e)
            results.append({
                "status": "error",
                "message": f"Failed to upload image to S3: {str(e)}",
            })

    return results


def handler(job):
    """
    The main function that handles a job of generating images.

    This function validates each workflow input, sends prompts to ComfyUI for processing,
    polls ComfyUI for results, and processes generated images as they become available.

    Args:
        job (dict): A dictionary containing job details and input parameters.

    Returns:
        dict: A dictionary containing either an error message or a success status with generated images.
    """
    s3_required_keys = ["BUCKET_ENDPOINT_URL", "BUCKET_ACCESS_KEY_ID", "BUCKET_SECRET_ACCESS_KEY", "S3_REGION", "S3_BUCKET_NAME"]
    s3_missing_keys = [key for key in s3_required_keys if not os.environ.get(key)]
    
    if len(s3_missing_keys) > 0:
        e = f"S3 configuration is missing or imcomplete, missing key(s): {s3_missing_keys}"
        logger.error(e, extra={})
        return {"error": e}

    job_input = job["input"]
    workflows = job_input.get("workflow", [])
    inference_job_id = job_input.get("inferenceJobId")

    if not workflows or len(workflows) == 0:
        logger.error("No workflows provided", extra={})
        return {"error": "No workflows provided"}

    validated_workflows = []
    for workflow in workflows:
        logger.info("Validating workflow", extra={})
        validated_data, error_message = validate_input({"workflow": workflow})

        if error_message:
            logger.error("Workflow validation failed", extra={"error": error_message})
            return {"error": error_message}

        validated_workflows.append(validated_data)

    # Make sure that the ComfyUI API is available
    check_server(
        f"http://{COMFY_HOST}",
        COMFY_API_AVAILABLE_MAX_RETRIES,
        COMFY_API_AVAILABLE_INTERVAL_MS,
    )

    # Upload images if they exist
    images = job_input.get("images")
    upload_result = upload_images(images)
    if upload_result["status"] == "error":
        logger.error("Image upload failed", extra={"upload_result": upload_result})
        return upload_result

    prompt_ids = []

    # Validate and queue each workflow
    try:
        for validated_data in validated_workflows:
            queued_workflow = queue_workflow(validated_data["workflow"])
            prompt_id = queued_workflow["prompt_id"]
            prompt_ids.append(prompt_id)
            logger.info("Queued workflow", extra={"prompt_id": prompt_id})
    except Exception as e:
        logger.error("Error queuing workflows", extra={"error": str(e)})
        return {"error": f"Error queuing workflows: {str(e)}"}

    # Poll for completion of workflows and process images as they become available
    logger.info("Waiting for image generation and processing images as they complete", extra={})
    retries = 0
    completed_prompt_ids = set()
    images_results = []

    try:
        while retries < COMFY_POLLING_MAX_RETRIES and len(completed_prompt_ids) < len(prompt_ids):
            for prompt_id in prompt_ids:
                # Skip prompts we've already processed
                if prompt_id in completed_prompt_ids:
                    continue
                    
                history = get_history(prompt_id)

                # Check if this prompt has completed
                if prompt_id in history and history[prompt_id].get("outputs"):
                    logger.info("Workflow completed, processing results", extra={"prompt_id": prompt_id})
                    
                    # Process the images for this completed workflow immediately
                    outputs = history[prompt_id].get("outputs")
                    images_result = process_output_images(outputs, job["id"], inference_job_id)
                    # spread the images_result into the images_results array                    
                    images_results.extend(images_result)
                    
                    # Mark this prompt as processed
                    completed_prompt_ids.add(prompt_id)
            
            # If all prompts are completed, break out of the loop
            if len(completed_prompt_ids) == len(prompt_ids):
                break
                
            # Wait before checking again
            time.sleep(COMFY_POLLING_INTERVAL_MS / 1000)
            retries += 1

        # Check if we hit the retry limit
        if len(completed_prompt_ids) < len(prompt_ids):
            logger.error("Max retries reached while waiting for image generation", extra={})
            return {"error": "Max retries reached while waiting for image generation"}

    except Exception as e:
        logger.error("Error waiting for image generation", extra={"error": str(e)})
        return {"error": f"Error waiting for image generation: {str(e)}"}

    result = {"result": images_results, "refresh_worker": REFRESH_WORKER}
    logger.info("Image generation completed successfully", extra={"result": result})

    return result

def get_boto_client(
) -> Tuple[
    boto3.client, TransferConfig
]:
    """
    Returns a boto3 client and transfer config for the bucket.
    """
    bucket_session = boto3.session.Session()

    boto_config = Config(
        signature_version="s3v4", retries={"max_attempts": 3, "mode": "standard"}
    )

    transfer_config = TransferConfig(
        multipart_threshold=1024 * 25,
        max_concurrency=multiprocessing.cpu_count(),
        multipart_chunksize=1024 * 25,
        use_threads=True,
    )
    
    boto_client = bucket_session.client(
        "s3",
        endpoint_url=BUCKET_ENDPOINT_URL,
        aws_access_key_id=BUCKET_ACCESS_KEY_ID,
        aws_secret_access_key=BUCKET_SECRET_ACCESS_KEY,
        config=boto_config,
        region_name=S3_REGION,
        )

    return boto_client, transfer_config

def upload_image(
    job_id,
    image_location,
    result_index=0,
    results_list=None,
):
    """
    Upload a single file to bucket storage.
    """
    image_name = str(uuid.uuid4())[:8]
    boto_client, _ = get_boto_client()
    file_extension = os.path.splitext(image_location)[1]
    content_type = "image/" + file_extension.lstrip(".")

    with open(image_location, "rb") as input_file:
        output = input_file.read()

    logger.info("Uploading image to bucket", extra={"bucket_name": S3_BUCKET_NAME, "job_id": job_id, "image_name": image_name, "file_extension": file_extension})
    boto_client.put_object(
        Bucket=f"{S3_BUCKET_NAME}",
        Key=f"{job_id}/{image_name}{file_extension}",
        Body=output,
        ContentType=content_type,
    )

    presigned_url = boto_client.generate_presigned_url(
        "get_object",
        Params={"Bucket": f"{S3_BUCKET_NAME}", "Key": f"{job_id}/{image_name}{file_extension}"},
        ExpiresIn=604800,
    )

    if results_list is not None:
        results_list[result_index] = presigned_url

    return presigned_url

# Start the handler only if this script is run directly
if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})
