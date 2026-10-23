
import hashlib
import json
from copy import deepcopy

from models import db, DecisionCache


def canonical_package_key(package, policy_revision):
    canonical_data = {
        "package": package,
        "policyRevision": policy_revision,
    }

    canonical_json = json.dumps(
        canonical_data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )

    return hashlib.sha256(
        canonical_json.encode("utf-8")
    ).hexdigest()


def get_cached_decision(package, policy_revision):
    key = canonical_package_key(package, policy_revision)

    record = DecisionCache.query.filter_by(cache_key=key).first()    

    if record is None:
        return None

    return deepcopy(record.decision)


def cache_decision(package, policy_revision, decision):
    key = canonical_package_key(package, policy_revision)

    record = DecisionCache.query.filter_by(cache_key=key).first()

    if record is None:
        record = DecisionCache(
            cache_key=key,
            decision=deepcopy(decision),
        )
        db.session.add(record)
        db.session.commit()
