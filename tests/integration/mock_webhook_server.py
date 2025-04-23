from flask import Flask, request, jsonify
import base64
import os
import hmac
import hashlib
import json
import atexit
import shutil

app = Flask(__name__)

# Keep track of received webhooks for testing
received_webhooks = []

@app.route('/webhook', methods=['POST'])
def receive_webhook():
    print(f"Webhook Server: Received webhook request")
    
    try:
        # Get the signature from headers
        signature = request.headers.get('X-Webhook-Signature')
        if not signature:
            print("Webhook Server ERROR: Missing signature header")
            return jsonify({"error": "Missing signature header"}), 401
        
        # Get webhook secret from environment
        webhook_secret = os.environ.get('RESULT_IMAGE_WEBHOOK_SECRET')
        if not webhook_secret:
            print("Webhook Server ERROR: Webhook secret not configured")
            return jsonify({"error": "Webhook secret not configured"}), 500
        
        # Verify signature
        payload = request.get_data()
        expected_signature = hmac.new(
            webhook_secret.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()
        
        if signature != expected_signature:
            print(f"Webhook Server ERROR: Invalid signature. Expected {expected_signature}, got {signature}")
            return jsonify({"error": "Invalid signature"}), 401
        
        # Parse the payload
        data = request.json
        job_id = data.get('job_id', 'unknown')
        print(f"Webhook Server: Processing webhook for job {job_id}")
        
        # Store the webhook data for validation
        received_webhooks.append(data)        
        return jsonify({"success": True})
    
    except Exception as e:
        print(f"Webhook Server ERROR: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/', methods=['GET'])
def health_check():
    return "Webhook Server OK"

# Function to clean up webhook data directory on exit
def cleanup():
    pass

atexit.register(cleanup)

if __name__ == '__main__':
    cleanup()
    
    # Run the server
    port = int(os.environ.get('WEBHOOK_PORT', 8189))
    app.run(host='0.0.0.0', port=port, debug=True, use_reloader=False) 