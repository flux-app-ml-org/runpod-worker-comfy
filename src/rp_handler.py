import uuid
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
        return None, "Please provide input"

    # Check if input is a string and try to parse it as JSON
    if isinstance(job_input, str):
        try:
            job_input = json.loads(job_input)
        except json.JSONDecodeError:
            return None, "Invalid JSON format in input"

    # Validate 'workflow' in input
    workflow = job_input.get("workflow")
    if workflow is None:
        return None, "Missing 'workflow' parameter"

    # Validate 'images' in input, if provided
    images = job_input.get("images")
    if images is not None:
        if not isinstance(images, list) or not all(
            "name" in image and "image" in image for image in images
        ):
            return (
                None,
                "'images' must be a list of objects with 'name' and 'image' keys",
            )

    # Return validated data and no error
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
                print(f"runpod-worker-comfy - API is reachable")
                return True
        except requests.RequestException as e:
            # If an exception occurs, the server may not be ready
            pass

        # Wait for the specified delay before retrying
        time.sleep(delay / 1000)

    print(
        f"runpod-worker-comfy - Failed to connect to server at {url} after {retries} attempts."
    )
    return False


def upload_images(images):
    """
    Upload a list of base64 encoded images to the ComfyUI server using the /upload/image endpoint.

    Args:
        images (list): A list of dictionaries, each containing the 'name' of the image and the 'image' as a base64 encoded string.
        server_address (str): The address of the ComfyUI server.

    Returns:
        list: A list of responses from the server for each image upload.
    """
    if not images:
        return {"status": "success", "message": "No images to upload", "details": []}

    responses = []
    upload_errors = []

    print(f"runpod-worker-comfy - image(s) upload")

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
        else:
            responses.append(f"Successfully uploaded {name}")

    if upload_errors:
        print(f"runpod-worker-comfy - image(s) upload with errors")
        return {
            "status": "error",
            "message": "Some images failed to upload",
            "details": upload_errors,
        }

    print(f"runpod-worker-comfy - image(s) upload complete")
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
    return json.loads(urllib.request.urlopen(req).read())


def get_history(prompt_id, logger: logging.Logger):
    """
    Retrieve the history of a given prompt using its ID

    Args:
        prompt_id (str): The ID of the prompt whose history is to be retrieved

    Returns:
        dict: The history of the prompt, containing all the processing steps and results
    """
    with urllib.request.urlopen(f"http://{COMFY_HOST}/history/{prompt_id}") as response:
        res = response.read()
        json = json.loads(res)
        logger.debug("Got history response", extra={"prompt_id": prompt_id, "json": json, "res": res})
        
        return json


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
        return f"{encoded_string}"


def process_output_images(outputs, job_id, logger):
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
    COMFY_OUTPUT_PATH = os.environ.get("COMFY_OUTPUT_PATH", "/comfyui/output")

    logger.info("started execution", extra={"outputs": outputs, "job_id": job_id, "output_path": COMFY_OUTPUT_PATH, "items": outputs.items()})
    output_images = []
    for node_id, node_output in outputs.items():
        if "images" in node_output:
            for image in node_output["images"]:
                image_path = os.path.join(image["subfolder"], image["filename"])
                output_images.append(image_path)

    logger.info("image generation is done", {"output_images": output_images})

    results = []
    local_image_paths = []

    for image_path in output_images:
        local_image_path = f"{COMFY_OUTPUT_PATH}/{image_path}"
        logger.info("got image path", extra={'local_image_path': local_image_path})

        if os.path.exists(local_image_path):
            local_image_paths.append(local_image_path)
        else:
            logger.error("the image does not exist in the output folder", extra={'image_path': image_path, "local_image_path": local_image_path})
            results.append({
                "status": "error",
                "message": f"the image does not exist in the specified output folder: {local_image_path}",
            })

    logger.info("collected all image paths", extra={'output_images': output_images})
    if os.environ.get("BUCKET_ENDPOINT_URL", False):
        # Upload all images at once
        logger.info("Uploading images to an s3 bucket")
        image_urls = rp_upload.files(job_id, local_image_paths)

        for image_url in image_urls:
            results.append({
                "status": "success",
                "message": image_url,
            })

        logger.info("Uploaded images to S3", extra={"image_urls": image_urls, "results": results})
        return results

    for local_image_path in local_image_paths:
        # Base64 encode each image
        image = base64_encode(local_image_path)
        results.append({
            "status": "success",
            "message": image,
        })
        print("runpod-worker-comfy - ")

    logger.info("the image was generated and converted to base64", extra={"results": results, "local_image_paths": local_image_paths})
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
    try:
        trace_id = str(uuid.uuid4())
        logger = logging.getLogger("custom_logger")
        logger.setLevel(logging.DEBUG)

        LOKI_URL = os.environ.get("LOKI_URL", False)
        if LOKI_URL:
            custom_handler = LokiLoggerHandler(
                url=os.environ["LOKI_URL"],
                labels={
                    "application": os.environ.get('LOKI_APP_NAME', 'runpod-worker-comfy'),
                    "environment": "production",
                    "trace_id": trace_id
                },
                label_keys={},
                timeout=10,
            )

            logger.addHandler(custom_handler)
        else:
            logger.warning("LOKI_URL not defined in env, wont send logs to grafana")

        logger.info("Got job", extra={'job': job})
        job_input = job["input"]
        workflows = job_input.get("workflow", [])

        if not workflows:
            ret = {"error": "No workflows provided"}
            logger.info("No job to run, exiting", extra={'return_value': ret})
            return ret

        validated_workflows = []
        for workflow in workflows:
            logger.info("validating workflow", extra={'workflow': workflow})
            validated_data, error_message = validate_input({"workflow": workflow})

            if error_message:
                ret = {"error": error_message}
                logger.info("Got error validating input, returning", extra={'return_value': ret})
                return ret

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
            logger.error("Error uploading image", extra={"upload_result": upload_result})
            return upload_result

        prompt_ids = []

        # Validate and queue each workflow
        try:
            for validated_data in validated_workflows:

                queued_workflow = queue_workflow(validated_data["workflow"])
                logger.info("Queuing workflow", extra={"queued_workflow": queued_workflow})
                prompt_id = queued_workflow["prompt_id"]
                prompt_ids.append(prompt_id)
                print(f"runpod-worker-comfy - queued workflow with ID {prompt_id}")
        except Exception as e:
            logger.error("Error queuing workflows", extra={"error": e})
            return {"error": f"Error queuing workflows: {str(e)}"}

        # Poll for completion of all workflows
        logger.info("Waiting for all workflows to complete", extra={'prompt_ids': prompt_ids})
        retries = 0
        completed_images = {}

        try:
            while retries < COMFY_POLLING_MAX_RETRIES:
                all_completed = True
                for prompt_id in prompt_ids:
                    history = get_history(prompt_id, logger)
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
                e = "Max retries reached while waiting for image generation"
                logger.error(e, extra={"retries": retries, })
                return {"error": e}

        except Exception as e:
            msg = "Error waiting for image generation"
            logger.error(msg, extra={"error": e})
            return {"error": f"{msg}: {str(e)}"}

        # Process and return all generated images
        images_results = []
        for prompt_id, outputs in completed_images.items():
            images_result = process_output_images(outputs, job["id"], logger)
            images_results.append(images_result)

        result = {"result": images_results, "refresh_worker": REFRESH_WORKER}
        logger.info("Returning result", extra={"result": result})
        return result
    except Exception as e:
        logger.error('Errored', extra={"error": e})
        return {"error": e}

# Start the handler only if this script is run directly
if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})
