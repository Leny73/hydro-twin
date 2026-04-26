from backend.lambda_handler import lambda_handler
import json

event = {
    "httpMethod": "POST",
    "body": json.dumps({
        "region_id": "pleven-small",
        "bbox": [24.5858, 43.3954, 24.6475, 43.4404]
    })
}

response = lambda_handler(event, None)
print(response["statusCode"])
print(json.loads(response["body"]))