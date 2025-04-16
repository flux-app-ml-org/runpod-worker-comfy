import runpod
from runpod.serverless.utils import rp_upload
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
from loki_logger_handler.loki_logger_handler import LokiLoggerHandler

# Time to wait between API check attempts in milliseconds
COMFY_API_AVAILABLE_INTERVAL_MS = 50
# Maximum number of API check attempts
COMFY_API_AVAILABLE_MAX_RETRIES = 500
# Time to wait between poll attempts in milliseconds
COMFY_POLLING_INTERVAL_MS = int(os.environ.get("COMFY_POLLING_INTERVAL_MS", 250))
# Maximum number of poll attempts
COMFY_POLLING_MAX_RETRIES = int(os.environ.get("COMFY_POLLING_MAX_RETRIES", 500))
# Host where ComfyUI is running
COMFY_HOST = "127.0.0.1:8188"
# Enforce a clean state after each job is done
# see https://docs.runpod.io/docs/handler-additional-controls#refresh-worker
REFRESH_WORKER = os.environ.get("REFRESH_WORKER", "false").lower() == "true"


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


def process_output_images(outputs, job_id):
    """
    This function takes the "outputs" from image generation and the job ID,
    then determines the correct way to return the image, either as a direct URL
    to an AWS S3 bucket or as a base64 encoded string, depending on the
    environment configuration.

    Args:
        outputs (dict): A dictionary containing the outputs from image generation,
                        typically includes node IDs and their respective output data.
        job_id (str): The unique identifier for the job.

    Returns:
        dict: A dictionary with the status ('success' or 'error') and the message,
              which is either the URL to the image in the AWS S3 bucket or a base64
              encoded string of the image. In case of error, the message details the issue.

    The function works as follows:
    - It first determines the output path for the images from an environment variable,
      defaulting to "/comfyui/output" if not set.
    - It then iterates through the outputs to find the filenames of the generated images.
    - After confirming the existence of the image in the output folder, it checks if the
      AWS S3 bucket is configured via the BUCKET_ENDPOINT_URL environment variable.
    - If AWS S3 is configured, it uploads the image to the bucket and returns the URL.
    - If AWS S3 is not configured, it encodes the image in base64 and returns the string.
    - If the image file does not exist in the output folder, it returns an error status
      with a message indicating the missing image file.
    """

    # The path where ComfyUI stores the generated images
    COMFY_OUTPUT_PATH = os.environ.get("COMFY_OUTPUT_PATH", "/comfyui/output")

    output_images = []

    logger.info("Processing output images", extra={"outputs": outputs})

    for node_id, node_output in outputs.items():
        if "images" in node_output:
            for image in node_output["images"]:
                image_path = os.path.join(image["subfolder"], image["filename"])
                output_images.append(image_path)

    logger.info("Image generation is done", extra={})

    results = []
    local_image_paths = []

    for image_path in output_images:
        local_image_path = f"{COMFY_OUTPUT_PATH}/{image_path}"
        logger.info("Checking local image path", extra={"local_image_path": local_image_path})

        if os.path.exists(local_image_path):
            local_image_paths.append(local_image_path)
        else:
            logger.error("The image does not exist in the output folder", extra={"local_image_path": local_image_path})
            results.append({
                "status": "error",
                "message": f"the image does not exist in the specified output folder: {local_image_path}",
            })

    if os.environ.get("BUCKET_ENDPOINT_URL", False):
        # Upload all images at once
        image_urls = rp_upload.files(job_id, local_image_paths)

        for image_url in image_urls:
            results.append({
                "status": "success",
                "message": image_url,
            })

        logger.info("Images were uploaded to AWS S3", extra={})

        return results

    for local_image_path in local_image_paths:
        # Base64 encode each image
        image = base64_encode(local_image_path)
        results.append({
            "status": "success",
            "message": image,
        })
        logger.info("The image was generated and converted to base64", extra={})

    return results


def handler(job):
    """
    The main function that handles a job of generating images.

    This function validates each workflow input, sends prompts to ComfyUI for processing,
    polls ComfyUI for results, and retrieves generated images.

    Args:
        job (dict): A dictionary containing job details and input parameters.

    Returns:
        dict: A dictionary containing either an error message or a success status with generated images.
    """
    job_input = job["input"]
    workflows = job_input.get("workflow", [])

    if not workflows:
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

    # Poll for completion of all workflows
    logger.info("Waiting until image generation is complete for all workflows", extra={})
    retries = 0
    completed_images = {}

    try:
        while retries < COMFY_POLLING_MAX_RETRIES:
            all_completed = True
            for prompt_id in prompt_ids:
                history = get_history(prompt_id)

                if prompt_id in history and history[prompt_id].get("outputs"):
                    completed_images[prompt_id] = history[prompt_id].get("outputs")
                else:
                    all_completed = False

            if all_completed:
                break
            else:
                # Wait before trying again
                time.sleep(COMFY_POLLING_INTERVAL_MS / 1000)
                retries += 1

        if not all_completed:
            logger.error("Max retries reached while waiting for image generation", extra={})
            return {"error": "Max retries reached while waiting for image generation"}

    except Exception as e:
        logger.error("Error waiting for image generation", extra={"error": str(e)})
        return {"error": f"Error waiting for image generation: {str(e)}"}

    # Process and return all generated images
    images_results = []
    for prompt_id, outputs in completed_images.items():
        images_result = process_output_images(outputs, job["id"])
        images_results.append(images_result)

    result = {"result": images_results, "refresh_worker": REFRESH_WORKER}
    logger.info("Image generation completed successfully", extra={"result": result})

    return result


# Start the handler only if this script is run directly
if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})
