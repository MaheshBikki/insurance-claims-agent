"""
Milestone 3 (cont.) - Settlement recommendation tool.

Deterministic, rule-based settlement logic - no LLM involved. This is
deliberate: the actual money-math (how much to pay out) should never be
left to an LLM's discretion. The agent's job (once wired up) is to call
this function and the fraud tool, then explain the combined result in
plain English - not to compute the payout itself.

Decision logic:
- If fraud risk is "high" -> escalate to a human adjuster, no auto-payout.
- If fraud risk is "medium" -> escalate as well; medium-risk claims still
  need human review under this design (deliberately conservative).
- If fraud risk is "low" -> auto-approve, payout = min(claim_amount,
  coverage_limit) - deductible, floored at 0.

This mirrors the "human-in-the-loop for high-risk claims" pattern real
insurers use - full auto-approval only for the clearly clean cases.
"""
import os

import psycopg2
import psycopg2.extras

from fraud_tool import check_claim_fraud_risk

DB_HOST = os.environ["DB_HOST"]
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_NAME = os.environ.get("DB_NAME", "claimsdb")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ["DB_PASSWORD"]


def get_connection():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD
    )


def get_claim_and_deductible(claim_id: str):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """
        SELECT c.claim_amount, p.coverage_limit, p.deductible
        FROM claims c
        JOIN policies p ON c.policy_id = p.policy_id
        WHERE c.claim_id = %s
        """,
        (claim_id,),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row


def recommend_settlement(claim_id: str) -> dict:
    """
    Combines the fraud-risk check with deterministic payout math to produce
    a final settlement recommendation. This is the function that ties
    Milestone 3's two tools together - the next step (Milestone 4) wraps
    THIS as the agent's final decision-making tool.

    Returns:
    {
        "claim_id": str,
        "found": bool,
        "decision": "approve" | "escalate" | "deny",
        "payout_amount": float,       # 0 if escalated or denied
        "risk_level": str,
        "reasoning": str,             # plain-English summary for the audit trail
        "fraud_flags": [str, ...],
    }
    """
    fraud_result = check_claim_fraud_risk(claim_id)

    if not fraud_result["found"]:
        return {"claim_id": claim_id, "found": False}

    claim_row = get_claim_and_deductible(claim_id)
    claim_amount = float(claim_row["claim_amount"])
    coverage_limit = float(claim_row["coverage_limit"])
    deductible = float(claim_row["deductible"])

    risk_level = fraud_result["risk_level"]
    flags = fraud_result["flags"]

    if risk_level in ("high", "medium"):
        decision = "escalate"
        payout_amount = 0.0
        reasoning = (
            f"Escalated to human adjuster due to {risk_level} fraud risk. "
            f"Flags: {'; '.join(flags) if flags else 'none'}."
        )
    else:
        capped_amount = min(claim_amount, coverage_limit)
        payout_amount = max(capped_amount - deductible, 0.0)
        decision = "approve"
        reasoning = (
            f"Auto-approved: low fraud risk, no flags raised. "
            f"Payout = min(claimed {claim_amount:.2f}, limit {coverage_limit:.2f}) "
            f"- deductible {deductible:.2f} = {payout_amount:.2f}."
        )

    return {
        "claim_id": claim_id,
        "found": True,
        "decision": decision,
        "payout_amount": round(payout_amount, 2),
        "risk_level": risk_level,
        "reasoning": reasoning,
        "fraud_flags": flags,
    }


if __name__ == "__main__":
    test_ids = ["CLM300116", "CLM300186", "CLM300001", "CLM300002", "CLM300081"]
    for cid in test_ids:
        result = recommend_settlement(cid)
        print(f"\n{cid}:")
        for k, v in result.items():
            print(f"  {k}: {v}")
