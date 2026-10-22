
import hashlib
import json
from copy import deepcopy

# In-memory cache for development.
# We will replace this with persistent storage before deployment.
_DECISION_CACHE = {}


def canonical_package_key(package, policy_revision):
    """Create a stable key from package content and policy."""
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

    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def get_cached_decision(package, policy_revision):
    key = canonical_package_key(package, policy_revision)
    decision = _DECISION_CACHE.get(key)
    return deepcopy(decision) if decision is not None else None


def cache_decision(package, policy_revision, decision):
    key = canonical_package_key(package, policy_revision)
    _DECISION_CACHE[key] = deepcopy(decision)
