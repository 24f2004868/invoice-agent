
import hashlib
import json
import os
import secrets
import uuid

from decision_engine import decide_batch
from flask import Flask, jsonify, request
from models import db, InvoiceTask, ProcessedReceipt, IdempotencyRecord, DecisionCache
from dotenv import load_dotenv
load_dotenv()

INPUT_MODE = "application/vnd.ga5.invoice-claim-batch+json"
PROPOSAL_MODE = "application/vnd.ga5.invoice-action-proposals+json"
RECEIPT_MODE = "application/vnd.ga5.invoice-action-receipts+json"

app = Flask(__name__)

database_url = os.getenv("DATABASE_URL", "sqlite:///invoice_agent.db")

if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Configure a real token in your local .env before testing protected routes.
app.config["A2A_BEARER_TOKEN"] = os.getenv("A2A_BEARER_TOKEN", "")

db.init_app(app)

with app.app_context():
    db.create_all()


@app.route("/")
def home():
    return jsonify({"message": "Invoice Agent is running"})


@app.route("/.well-known/agent-card.json", methods=["GET"])
def agent_card():
    base_url = os.getenv(
    "A2A_BASE_URL",
    "https://invoice-agent-17mh.onrender.com/a2a/"
)
    return jsonify({
        "name": "A2A Invoice Agent",
        "description": "An invoice agent that evaluates invoice evidence and proposes safe business actions.",
        "version": "1.0.0",
        "capabilities": {},
        "supportedInterfaces": [{
            "url": base_url,
            "protocolBinding": "HTTP+JSON",
            "protocolVersion": "1.0"
        }],
        "defaultInputModes": [
            "application/vnd.ga5.invoice-claim-batch+json"
        ],
        "defaultOutputModes": [
            "application/vnd.ga5.invoice-action-proposals+json",
            "application/vnd.ga5.invoice-action-receipts+json"
        ],
        "skills": [{
            "id": "invoice_action_agent",
            "name": "Invoice Action Agent",
            "description": "Reviews invoice evidence and proposes appropriate business actions.",
            "tags": ["invoice", "payments", "approval", "duplicate-detection"]
        }]
    })



def authenticated_principal():
    """Create a separate principal for each bearer token."""
    supplied = request.headers.get("Authorization", "")
    scheme, separator, token = supplied.partition(" ")

    if (
        not separator
        or scheme != "Bearer"
        or not token
        or token.strip() != token
    ):
        return None

    return hashlib.sha256(token.encode("utf-8")).hexdigest()



@app.before_request
def validate_protected_request():
    if request.path == "/.well-known/agent-card.json" or request.path == "/":
        return None

    if not request.path.startswith("/a2a/"):
        return jsonify({"error": "NOT_FOUND"}), 404

    if request.headers.get("A2A-Version") != "1.0":
        return jsonify({"error": "UNSUPPORTED_A2A_VERSION"}), 400

    principal = authenticated_principal()
    if principal is None:
        return jsonify({"error": "UNAUTHORIZED"}), 401

    request.environ["a2a.principal"] = principal

    if request.method == "POST":
        content_type = request.headers.get("Content-Type", "")
        if "application/a2a+json" not in content_type:
            return jsonify({"error": "UNSUPPORTED_MEDIA_TYPE"}), 415


def task_response(task):
    return {
        "id": task.task_id,
        "status": {"state": task.status},
        "history": task.history or [],
        "artifacts": [],
    }


@app.route("/a2a/tasks", methods=["GET"])
def list_tasks():
    principal = request.environ["a2a.principal"]
    tasks = InvoiceTask.query.filter_by(principal=principal).all()
    return jsonify({"tasks": [task_response(task) for task in tasks]})


@app.route("/a2a/tasks/<task_id>", methods=["GET"])
def get_task(task_id):
    principal = request.environ["a2a.principal"]
    task = InvoiceTask.query.filter_by(
        task_id=task_id,
        principal=principal,
    ).first()

    if task is None:
        return jsonify({"error": "TASK_NOT_FOUND"}), 404

    return jsonify(task_response(task))


@app.route("/a2a/tasks/<task_id>:cancel", methods=["POST"])
def cancel_task(task_id):
    principal = request.environ["a2a.principal"]
    task = InvoiceTask.query.filter_by(
        task_id=task_id,
        principal=principal,
    ).first()

    if task is None:
        return jsonify({"error": "TASK_NOT_FOUND"}), 404

    if task.status in ("TASK_STATE_COMPLETED", "TASK_STATE_CANCELED"):
        return jsonify({"error": "TASK_TERMINAL"}), 409

    task.status = "TASK_STATE_CANCELED"
    task.updated_at = db.func.current_timestamp()
    db.session.commit()

    return jsonify({"task": task_response(task)})


def canonical_json(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def message_parts(message):
    if not isinstance(message, dict):
        return None

    parts = message.get("parts")
    if not isinstance(parts, list):
        return None

    return parts


def task_artifacts(task):
    artifacts = []

    if task.proposals is not None:
        artifacts.append({
            "artifactId": f"{task.task_id}-proposals",
            "parts": [{
                "mediaType": PROPOSAL_MODE,
                "data": task.proposals,
            }],
        })

    if task.receipts is not None:
        artifacts.append({
            "artifactId": f"{task.task_id}-receipts",
            "parts": [{
                "mediaType": RECEIPT_MODE,
                "data": task.receipts,
            }],
        })

    return artifacts


def task_response(task):
    artifacts = []

    if task.proposals:
        artifacts.append({
            "artifactId": f"{task.task_id}-proposals",
            "parts": [{
                "mediaType": "application/vnd.ga5.invoice-action-proposals+json",
                "data": task.proposals
            }]
        })

    if task.receipts:
        artifacts.append({
            "artifactId": f"{task.task_id}-receipts",
            "parts": [{
                "mediaType": "application/vnd.ga5.invoice-action-receipts+json",
                "data": task.receipts
            }]
        })

    return {
        "id": task.task_id,
        "status": {"state": task.status},
        "history": task.history or [],
        "artifacts": artifacts,
        "executions": task.executions or []
    }


@app.route("/a2a/message:send", methods=["POST"])
def send_message():
    body = request.get_json(silent=True)

    if not isinstance(body, dict):
        return jsonify({"error": "INVALID_JSON"}), 400

    message = body.get("message")
    if not isinstance(message, dict):
        return jsonify({"error": "INVALID_MESSAGE"}), 400

    if message.get("role") != "ROLE_USER":
        return jsonify({"error": "INVALID_MESSAGE_ROLE"}), 400

    message_id = message.get("messageId")
    if not isinstance(message_id, str) or not message_id.strip():
        return jsonify({"error": "MESSAGE_ID_REQUIRED"}), 400

    parts = message_parts(message)
    if parts is None or len(parts) != 1:
        return jsonify({"error": "INVALID_MESSAGE_PARTS"}), 400

    
    part = parts[0]
    if not isinstance(part, dict):
        return jsonify({"error": "INVALID_MESSAGE_PART"}), 400

    media_type = part.get("mediaType")

    if media_type not in (
        INPUT_MODE,
        "application/vnd.ga5.invoice-action-results+json",
    ):
        return jsonify({"error": "UNSUPPORTED_INPUT_MODE"}), 400

    
    # Handle receipt results separately from new invoice batches.
    if media_type == "application/vnd.ga5.invoice-action-results+json":
        return process_receipt_message(
            message=message,
            message_id=message_id,
            part=part,
            principal=request.environ["a2a.principal"],
        )



    data = part.get("data")
    if not isinstance(data, dict):
        return jsonify({"error": "INVALID_BATCH_DATA"}), 400

    batch_id = data.get("batchId")
    policy_revision = data.get("policyRevision")
    packages = data.get("packages")

    if (
        not isinstance(batch_id, str)
        or not batch_id
        or not isinstance(policy_revision, str)
        or not policy_revision
        or not isinstance(packages, list)
        or not packages
    ):
        return jsonify({"error": "INVALID_BATCH_DATA"}), 400

    principal = request.environ["a2a.principal"]

    # Idempotency is based on the message only, not configuration.
    request_hash = hashlib.sha256(
        canonical_json(message).encode("utf-8")
    ).hexdigest()

    existing = IdempotencyRecord.query.filter_by(
        principal=principal,
        message_id=message_id,
    ).first()

    if existing:
        if existing.request_hash != request_hash:
            return jsonify({"error": "IDEMPOTENCY_CONFLICT"}), 409

        task = InvoiceTask.query.filter_by(
            task_id=existing.task_id,
            principal=principal,
        ).first()

        if task is None:
            return jsonify({"error": "TASK_NOT_FOUND"}), 404

        return jsonify({"task": task_response(task)}), 200

    package_ids = [
        p.get("packageId")
        for p in packages
        if isinstance(p, dict)
    ]

    if (
        len(package_ids) != len(packages)
        or any(not isinstance(pid, str) or not pid for pid in package_ids)
        or len(set(package_ids)) != len(package_ids)
    ):
        return jsonify({"error": "INVALID_PACKAGE_IDS"}), 400

    # Ask the decision engine for one decision per package.
    try:
        decisions = decide_batch(packages, policy_revision)
    except Exception:
        app.logger.exception("Invoice decision generation failed")
        return jsonify({"error": "DECISION_GENERATION_FAILED"}), 502

    if len(decisions) != len(packages):
        return jsonify({"error": "INVALID_DECISION_COUNT"}), 502

    decisions_by_id = {
        str(decision.get("packageId")): decision
        for decision in decisions
    }

    if (
        len(decisions_by_id) != len(decisions)
        or set(decisions_by_id) != set(package_ids)
    ):
        return jsonify({"error": "INVALID_DECISION_IDS"}), 502

    proposals = []

    for package in packages:
        package_id = package["packageId"]
        decision = decisions_by_id[package_id]

        documents = package.get("documents", [])
        if not isinstance(documents, list):
            return jsonify({"error": "INVALID_DOCUMENTS"}), 400

        available_refs = set()
        for document in documents:
            if not isinstance(document, dict):
                continue
            text = document.get("text", "")
            if isinstance(text, str):
                # Extract bracketed source references such as [INV-001].
                import re
                available_refs.update(
                    re.findall(r"\[([A-Za-z0-9_-]+)\]", text)
                )

        evidence_refs = decision.get("evidenceRefs")       
        if (
            not isinstance(evidence_refs, list)
            or len(evidence_refs) != 3
            or len(set(evidence_refs)) != 3
            or any(ref not in available_refs for ref in evidence_refs)
        ):
            return jsonify({
                "error": "INVALID_EVIDENCE_REFERENCES",
                "packageId": package_id,
            }), 502

        action = decision.get("action")
        allowed_actions = {
            "settle_invoice",
            "request_approval",
            "hold_invoice",
            "reject_duplicate",
            "open_exception",
        }
        if action not in allowed_actions:
            return jsonify({"error": "INVALID_ACTION"}), 502

        rationale = decision.get("rationale", "")
        if not isinstance(rationale, str) or not 60 <= len(rationale) <= 1500:
            return jsonify({"error": "INVALID_RATIONALE"}), 502

        # Keep action IDs durable and stable for the same package decision.
        action_id = decision.get("actionId")
        if not isinstance(action_id, str) or len(action_id) < 12:
            identity = canonical_json({
                "package": package,
                "policyRevision": policy_revision,
                "action": action,
            })
            action_id = "act_" + hashlib.sha256(
                identity.encode("utf-8")
            ).hexdigest()[:32]

        proposals.append({
            "packageId": package_id,
            "actionId": action_id,
            "action": action,
            "facts": {
                "vendorName": decision.get("vendorName", ""),
                "invoiceNumber": decision.get("invoiceNumber", ""),
                "amountMinor": decision.get("amountMinor"),
                "currency": decision.get("currency", ""),
            },
            "evidenceRefs": evidence_refs,
            "rationale": rationale,
        })

    if len({p["actionId"] for p in proposals}) != len(proposals):
        return jsonify({"error": "DUPLICATE_ACTION_IDS"}), 502

    task_id = str(uuid.uuid4())

    task = InvoiceTask(
        task_id=task_id,
        principal=principal,
        status="TASK_STATE_INPUT_REQUIRED",
        batch_id=batch_id,
        policy_revision=policy_revision,
        invoice_data=data,
        proposals={
            "batchId": batch_id,
            "proposals": proposals,
        },
        receipts=None,
        history=[message],
        executions=[],
    )

    idempotency = IdempotencyRecord(
        principal=principal,
        message_id=message_id,
        request_hash=request_hash,
        task_id=task_id,
    )

    try:
        db.session.add(task)
        db.session.flush()
        db.session.add(idempotency)
        db.session.commit()
    except Exception:
        db.session.rollback()
        app.logger.exception("Could not save invoice task")
        return jsonify({"error": "TASK_PERSISTENCE_FAILED"}), 500

    return jsonify({"task": task_response(task)}), 200


def process_receipt_message(message, message_id, part, principal):
    data = part.get("data")

    if not isinstance(data, dict):
        return jsonify({"error": "INVALID_RECEIPT_DATA"}), 400

    batch_id = data.get("batchId")
    results = data.get("results")

    if not isinstance(batch_id, str) or not isinstance(results, list):
        return jsonify({"error": "INVALID_RECEIPT_DATA"}), 400

        principal = principal
    request_hash = hashlib.sha256(
        canonical_json(message).encode("utf-8")
    ).hexdigest()

    existing = IdempotencyRecord.query.filter_by(
        principal=principal,
        message_id=message_id,
    ).first()

    if existing:
        if existing.request_hash != request_hash:
            return jsonify({"error": "IDEMPOTENCY_CONFLICT"}), 409

        existing_task = InvoiceTask.query.filter_by(
            task_id=existing.task_id,
            principal=principal,
        ).first()

        if existing_task is None:
            return jsonify({"error": "TASK_NOT_FOUND"}), 404

        return jsonify({"task": task_response(existing_task)}), 200
    
    task_id = message.get("taskId")
    if not isinstance(task_id, str) or not task_id:
        return jsonify({"error": "TASK_ID_REQUIRED"}), 400

    task = InvoiceTask.query.filter_by(
        task_id=task_id,
        principal=principal
    ).first()

    if task is None:
        return jsonify({"error": "TASK_NOT_FOUND"}), 404

    if task.batch_id != batch_id:
        return jsonify({"error": "BATCH_MISMATCH"}), 400

    if task.status != "TASK_STATE_INPUT_REQUIRED":
        return jsonify({"error": "TASK_NOT_ACCEPTING_RESULTS"}), 409

    proposals = (task.proposals or {}).get("proposals", [])
    proposal_by_id = {p.get("packageId"): p for p in proposals}

    if not results:
        return jsonify({"error": "RESULTS_REQUIRED"}), 400

    seen = set()
    accepted_executions = []
    receipts = []

    for result in results:
        if not isinstance(result, dict):
            return jsonify({"error": "INVALID_RESULT"}), 400

        package_id = result.get("packageId")
        action_id = result.get("actionId")
        action = result.get("action")
        outcome = result.get("outcome")
        nonce = result.get("receiptNonce")

        if not all(isinstance(v, str) and v for v in (
            package_id, action_id, action, outcome, nonce
        )):
            return jsonify({"error": "INVALID_RESULT"}), 400

        if package_id in seen:
            return jsonify({"error": "DUPLICATE_RESULT"}), 400
        seen.add(package_id)

        proposal = proposal_by_id.get(package_id)
        if proposal is None:
            return jsonify({"error": "UNKNOWN_PACKAGE"}), 400

        if (
            proposal.get("actionId") != action_id
            or proposal.get("action") != action
        ):
            return jsonify({"error": "PROPOSAL_MISMATCH"}), 400

        if outcome not in ("ACCEPTED", "REJECTED"):
            return jsonify({"error": "INVALID_OUTCOME"}), 400

        receipt = {
            "packageId": package_id,
            "actionId": action_id,
            "action": action,
            "outcome": outcome,
            "receiptNonce": nonce,
        }
        receipts.append(receipt)

        if outcome == "ACCEPTED":
            accepted_executions.append(receipt.copy())

    
    # Save the task and idempotency record together.
    task.receipts = {"batchId": batch_id, "receipts": receipts}
    task.executions = accepted_executions
    task.status = "TASK_STATE_COMPLETED"

    history = list(task.history or [])
    history.append(message)
    task.history = history

    idempotency = IdempotencyRecord(
        principal=principal,
        message_id=message_id,
        request_hash=request_hash,
        task_id=task.task_id,
    )

    try:
        db.session.add(idempotency)
        db.session.commit()
    except Exception:
        db.session.rollback()
        app.logger.exception("Could not save receipt and idempotency record")
        return jsonify({"error": "RECEIPT_PERSISTENCE_FAILED"}), 500

    return jsonify({"task": task_response(task)}), 200




if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
