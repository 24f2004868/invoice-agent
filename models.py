
from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def utc_now():
    return datetime.now(timezone.utc)


class InvoiceTask(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.String(100), unique=True, nullable=False, index=True)
    principal = db.Column(db.String(64), nullable=False, index=True)
    status = db.Column(db.String(30), default="submitted", nullable=False)
    batch_id = db.Column(db.String(150), nullable=False)
    policy_revision = db.Column(db.String(150), nullable=False)
    invoice_data = db.Column(db.JSON, nullable=False)
    proposals = db.Column(db.JSON)
    receipts = db.Column(db.JSON)
    history = db.Column(db.JSON, nullable=False, default=list)
    executions = db.Column(db.JSON, nullable=False, default=list)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now)
    updated_at = db.Column(db.DateTime(timezone=True), default=utc_now)


class ProcessedReceipt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    receipt_id = db.Column(db.String(150), unique=True, nullable=False)
    task_id = db.Column(
        db.String(100),
        db.ForeignKey("invoice_task.task_id"),
        nullable=False,
        index=True,
    )
    action = db.Column(db.String(50), nullable=False)
    processed_at = db.Column(db.DateTime(timezone=True), default=utc_now)


class IdempotencyRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    principal = db.Column(db.String(64), nullable=False)
    message_id = db.Column(db.String(200), nullable=False)
    request_hash = db.Column(db.String(64), nullable=False)
    task_id = db.Column(
        db.String(100),
        db.ForeignKey("invoice_task.task_id"),
        nullable=False,
    )
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now)

    __table_args__ = (
        db.UniqueConstraint(
            "principal",
            "message_id",
            name="uq_idempotency_principal_message",
        ),
    )


class DecisionCache(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cache_key = db.Column(db.String(64), unique=True, nullable=False, index=True)
    decision = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now)
