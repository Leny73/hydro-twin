"""
local_server.py — Local development server for HydroTwin backend
====================================================================

Wraps the Lambda handler in a minimal Flask HTTP server so you can
run and test the backend on your laptop without deploying to AWS.

Usage:
    # 1. Install dependencies (one-time)
    pip install flask flask-cors requests boto3 python-dotenv

    # 2. Copy and fill in .env.local
    cp .env.example .env.local

    # 3. Run
    python local_server.py

    # 4. Test with curl (or point VITE_API_ENDPOINT to http://localhost:5050/assess)
    curl -X POST http://localhost:5050/assess \
         -H "Content-Type: application/json" \
         -d '{"region_id": "danube-basin", "bbox": [8.0, 42.0, 30.0, 52.0]}'

AWS credentials for Bedrock:
    Set in .env.local:
        AWS_ACCESS_KEY_ID     = ...
        AWS_SECRET_ACCESS_KEY = ...
        AWS_DEFAULT_REGION    = us-east-1   (or whichever region has Bedrock)
    OR configure via the AWS CLI:
        aws configure
"""

import json
import os

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS

# Load .env.local first, then fall back to .env.example values
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env.local"),  override=True)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env.example"), override=False)

# Import the Lambda handler — it works identically outside of Lambda
from lambda_handler import lambda_handler

app = Flask(__name__)

# Allow all origins in local dev — matches the CORS headers set in the Lambda itself
CORS(app, resources={r"/*": {"origins": "*"}})


@app.route("/assess", methods=["POST", "OPTIONS"])
def assess():
    """
    Mimics the API Gateway → Lambda invocation locally.
    POST /assess  with JSON body  { "region_id": "...", "bbox": [...] }
    """
    if request.method == "OPTIONS":
        # Respond to CORS preflight
        return "", 204

    # Build a fake API Gateway event from the Flask request
    fake_event = {
        "httpMethod": "POST",
        "body":       request.get_data(as_text=True) or "{}",
        "headers":    dict(request.headers),
    }

    # Invoke the Lambda handler as if it were running in AWS
    result = lambda_handler(fake_event, context=None)

    response_body   = json.loads(result.get("body", "{}"))
    response_status = result.get("statusCode", 200)

    return jsonify(response_body), response_status


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "HydroTwin local dev server"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    print(f"\n  HydroTwin backend running at  http://localhost:{port}")
    print(f"  Health check:                   http://localhost:{port}/health")
    print(f"  Assess endpoint:                http://localhost:{port}/assess  (POST)\n")
    print(f"  Set VITE_API_ENDPOINT=http://localhost:{port}/assess in frontend/.env.local\n")
    app.run(host="0.0.0.0", port=port, debug=True)
