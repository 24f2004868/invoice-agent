
from decision_engine import decide_batch
from decision_cache import get_cached_decision

# Fictional test data only — no real financial records.
packages = [
    {
        "packageId": "TEST-PACKAGE-001",
        "documents": [
            {
                "type": "invoice",
                "text": (
                    "[INV-001] Vendor: Sample Supplies Ltd. "
                    "Invoice: SS-1001. Amount: INR 1250.00. "
                    "Currency: INR."
                ),
            },
            {
                "type": "purchase_order",
                "text": (
                    "[PO-001] Purchase order SS-1001 is approved "
                    "for Sample Supplies Ltd. for INR 1250.00."
                ),
            },
            {
                "type": "goods_receipt",
                "text": (
                    "[GRN-001] Goods for purchase order SS-1001 "
                    "were received and verified."
                ),
            },
        ],
    }
]

try:
    decisions = decide_batch(
        packages,
        policy_revision="test-policy-1",
    )

    for decision in decisions:
        print("\nFirst decision:")
        print(decision)

    print("\nCalling the decision engine again with the same package...")

    second_decisions = decide_batch(
        packages,
        policy_revision="test-policy-1",
    )

    print("\nSecond decision:")
    print(second_decisions[0])

    print(
        "\nSame actionId:",
        decisions[0]["actionId"] == second_decisions[0]["actionId"],
    )
    cached = get_cached_decision(
    packages[0],
    policy_revision="test-policy-1",
    )

    print("\nCache hit:", cached is not None)
    print("Cached actionId:", cached["actionId"] if cached else None)

except Exception as error:
    print("Test failed:", type(error).__name__)
    print("Details:", str(error)[:1000])
