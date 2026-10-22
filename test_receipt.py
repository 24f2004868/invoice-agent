
import json
import os
import urllib.request
import urllib.error
from dotenv import load_dotenv

load_dotenv()
token = os.getenv("A2A_BEARER_TOKEN")

body = {
    "message": {
        "messageId": "test-receipt-message-002",
        "taskId": "3d8a224f-5d43-4fd3-b5d6-bb2abf4a9664",
        "role": "ROLE_USER",
        "parts": [{
            "mediaType": "application/vnd.ga5.invoice-action-results+json",
            "data": {
                "batchId": "test-batch-003",
                "results": [{
                    "packageId": "TEST-PACKAGE-003",
                    "actionId": "act_106337fe96c230acb89d0426f7e7a356",
                    "action": "settle_invoice",
                    "outcome": "ACCEPTED",
                    "receiptNonce": "test-nonce-CHANGED"
                }]
            }
        }]
    }
}

request = urllib.request.Request(
    "https://invoice-agent-17mh.onrender.com/a2a/message:send",
    data=json.dumps(body).encode("utf-8"),
    headers={
        "Authorization": f"Bearer {token}",
        "A2A-Version": "1.0",
        "Content-Type": "application/a2a+json"
    },
    method="POST"
)

try:
    with urllib.request.urlopen(request, timeout=45) as response:
        print("HTTP status:", response.status)
        print(response.read().decode("utf-8"))
except urllib.error.HTTPError as error:
    print("HTTP error:", error.code)
    print(error.read().decode("utf-8"))
except Exception as error:
    print(type(error).__name__ + ":", error)
