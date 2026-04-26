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

# Import the Lambda handlers — they work identically outside of Lambda
from lambda_handler    import lambda_handler as assess_handler
from subscribe_handler import lambda_handler as subscribe_handler
from status_handler    import lambda_handler as status_handler
from cron_handler      import lambda_handler as cron_handler
from reports_handler   import lambda_handler as reports_handler
from chat_handler      import lambda_handler as chat_handler
from dams_handler      import lambda_handler as dams_handler

app = Flask(__name__)

# Allow all origins in local dev — matches the CORS headers set in the Lambda itself
CORS(app, resources={r"/*": {"origins": "*"}})


def _invoke_lambda(handler):
    """Build a fake API Gateway event from the current Flask request and invoke handler."""
    fake_event = {
        "httpMethod": request.method,
        "body":       request.get_data(as_text=True) or "{}",
        "headers":    dict(request.headers),
    }
    result          = handler(fake_event, context=None)
    response_body   = json.loads(result.get("body", "{}"))
    response_status = result.get("statusCode", 200)
    return jsonify(response_body), response_status


@app.route("/assess", methods=["POST", "OPTIONS"])
def assess():
    """POST /assess  with JSON body  { "region_id": "...", "bbox": [...] }"""
    if request.method == "OPTIONS":
        return "", 204
    return _invoke_lambda(assess_handler)


@app.route("/subscribe", methods=["POST", "OPTIONS"])
def subscribe():
    """POST /subscribe  with JSON body  { "email": "...", "region_id": "..." }"""
    if request.method == "OPTIONS":
        return "", 204
    return _invoke_lambda(subscribe_handler)


@app.route("/status", methods=["GET", "OPTIONS"])
def status():
    """GET /status — returns the latest snapshot per region."""
    if request.method == "OPTIONS":
        return "", 204
    return _invoke_lambda(status_handler)


@app.route("/reports", methods=["GET", "POST", "OPTIONS"])
def reports():
    """GET /reports → list all · POST /reports → submit a new incident report."""
    if request.method == "OPTIONS":
        return "", 204
    return _invoke_lambda(reports_handler)


@app.route("/chat-alert", methods=["POST", "OPTIONS"])
def chat_alert():
    """POST /chat-alert — context-aware HydroSentry assistant."""
    if request.method == "OPTIONS":
        return "", 204
    return _invoke_lambda(chat_handler)


@app.route("/dams", methods=["GET", "OPTIONS"])
def dams():
    """GET /dams — returns current status for all monitored dams."""
    if request.method == "OPTIONS":
        return "", 204
    return _invoke_lambda(dams_handler)


@app.route("/cron-run", methods=["POST"])
def cron_run():
    """
    POST /cron-run — manually trigger the cron orchestrator (local-dev only).
    In AWS this is invoked by EventBridge Scheduler, not over HTTP.
    """
    summary = cron_handler({}, context=None)
    return jsonify(summary), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "HydroTwin local dev server"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    print(f"\n  HydroTwin backend running at  http://localhost:{port}")
    print(f"  Health check:                   http://localhost:{port}/health")
    print(f"  Assess endpoint:                http://localhost:{port}/assess     (POST)")
    print(f"  Subscribe endpoint:             http://localhost:{port}/subscribe  (POST)")
    print(f"  Status endpoint:                http://localhost:{port}/status     (GET)")
    print(f"  Reports endpoint:               http://localhost:{port}/reports    (GET, POST)")
    print(f"  Chat assistant:                 http://localhost:{port}/chat-alert (POST)")
    print(f"  Manual cron run:                http://localhost:{port}/cron-run   (POST)\n")
    print(f"  Set VITE_API_ENDPOINT=http://localhost:{port}/assess in frontend/.env.local\n")
    app.run(host="0.0.0.0", port=port, debug=True)
