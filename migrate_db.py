
from sqlalchemy import inspect

from app import app, db
from models import IdempotencyRecord, DecisionCache

with app.app_context():
    inspector = inspect(db.engine)
    tables = inspector.get_table_names()

    # Create any newly added tables.
    db.create_all()

    # Add columns to an existing invoice_task table if missing.
    if "invoice_task" in tables:
        columns = {
            column["name"]
            for column in inspect(db.engine).get_columns("invoice_task")
        }

        additions = {
            "principal": "VARCHAR(64)",
            "batch_id": "VARCHAR(150)",
            "policy_revision": "VARCHAR(150)",
            "history": "JSON",
            "executions": "JSON",
            "updated_at": "DATETIME",
        }

        with db.engine.begin() as connection:
            for name, sql_type in additions.items():
                if name not in columns:
                    connection.exec_driver_sql(
                        f"ALTER TABLE invoice_task ADD COLUMN {name} {sql_type}"
                    )

            # Existing tasks get safe placeholder values.
            connection.exec_driver_sql(
                "UPDATE invoice_task SET principal = 'legacy' "
                "WHERE principal IS NULL"
            )
            connection.exec_driver_sql(
                "UPDATE invoice_task SET batch_id = 'legacy' "
                "WHERE batch_id IS NULL"
            )
            connection.exec_driver_sql(
                "UPDATE invoice_task SET policy_revision = 'legacy' "
                "WHERE policy_revision IS NULL"
            )
            connection.exec_driver_sql(
                "UPDATE invoice_task SET history = '[]' WHERE history IS NULL"
            )
            connection.exec_driver_sql(
                "UPDATE invoice_task SET executions = '[]' "
                "WHERE executions IS NULL"
            )
            connection.exec_driver_sql(
                "UPDATE invoice_task SET updated_at = CURRENT_TIMESTAMP "
                "WHERE updated_at IS NULL"
            )

    print("Database migration completed.")
    print("Tables:", inspect(db.engine).get_table_names())
