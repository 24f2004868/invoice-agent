
import json
import os
import urllib.request
import urllib.error
from dotenv import load_dotenv

load_dotenv()

token = os.getenv("A2A_BEARER_TOKEN")
if not token:
    raise RuntimeError("A2A_BEARER_TOKEN is missing from .env")

body = {
    "message": {
        "messageId": "test-message-003",
        "role": "ROLE_USER",
        "parts": [{
            "mediaType": "application/vnd.ga5.invoice-claim-batch+json",
            "data": {
                "batchId": "test-batch-003",
                "policyRevision": "test-policy-1",
                "packages": [{
                    "packageId": "TEST-PACKAGE-003",
                    "documents": [
                        {
                            "type": "invoice",
                            "text": "[INV-001] Vendor: Sample Supplies Ltd. Invoice: SS-1001. Amount: INR 1250.00. Currency: INR."
                        },
                        {
                            "type": "purchase_order",
                            "text": "[PO-001] Purchase order SS-1001 is approved for Sample Supplies Ltd. for INR 1250.00."
                        },
                        {
                            "type": "goods_receipt",
                            "text": "[GRN-001] Goods for purchase order SS-1001 were received and verified."
                        }
                    ]
                }]
            }
        }]
    },
    "configuration": {
        "returnImmediately": False,
        "historyLength": 20,
        "acceptedOutputModes": [
            "application/vnd.ga5.invoice-action-proposals+json"
        ]
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
