"""
Milestone 3 - Fraud/Anomaly check tool.

This is a plain Python function today - no agent framework or LLM involved yet.
That's deliberate: the logic should be correct and independently testable BEFORE
wrapping it as an agent tool. Once Bedrock quota clears, this function becomes
the "tool" an agent calls via function-calling - the function signature and
return shape below are already written in that shape (clear docstring, typed
inputs, structured dict output) so the wrapping step later is trivial.

Fraud signals checked (mirrors what we validated by hand in psql):
1. Claim amount is a high percentage of the coverage limit AND filed within
   days of policy start - classic "early large claim" pattern.
2. Claim's incident date falls after the policy's end date - claiming for an
   incident that happened (or was reported) after coverage lapsed.

NOTE on a bug we found and fixed: an earlier version also flagged "policy is
expired right now" on its own. That turned out to be wrong - it fired on 67%
of all claims (3,333 of 5,000) simply because time had passed since the claim
was filed, not because anything was actually suspicious. Policies naturally
expire; that alone is not a fraud signal. Only claiming for an incident that
happened AFTER the policy had already lapsed (flag #2 above) is meaningful.
"""
import os
from datetime import date

import psycopg2
import psycopg2.extras

DB_HOST = os.environ["DB_HOST"]
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_NAME = os.environ.get("DB_NAME", "claimsdb")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ["DB_PASSWORD"]

# Thresholds - pulled out as constants so they're easy to tune/justify in an interview
NEAR_LIMIT_THRESHOLD = 0.85      # claim amount as a fraction of coverage limit
EARLY_CLAIM_WINDOW_DAYS = 7      # "suspiciously soon after policy start"


def get_connection():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD
    )


def check_claim_fraud_risk(claim_id: str) -> dict:
    """
    Looks up a single claim by ID and returns a structured fraud-risk
    assessment. This is the function that will become an agent tool.

    Returns a dict shaped for direct JSON serialization back to an LLM:
    {
        "claim_id": str,
        "found": bool,
        "risk_level": "low" | "medium" | "high",
        "flags": [str, ...],          # human-readable reasons, empty if none
        "claim_amount": float,
        "coverage_limit": float,
        "pct_of_limit": float,
        "policy_status_live": "active" | "expired",
        "days_since_policy_start": int,
    }
    """
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute(
        """
        SELECT c.claim_id, c.claim_amount, c.incident_date,
               p.coverage_limit, p.start_date, p.end_date
        FROM claims c
        JOIN policies p ON c.policy_id = p.policy_id
        WHERE c.claim_id = %s
        """,
        (claim_id,),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()

    if row is None:
        return {"claim_id": claim_id, "found": False}

    pct_of_limit = float(row["claim_amount"]) / float(row["coverage_limit"])
    days_since_start = (row["incident_date"] - row["start_date"]).days
    policy_status_live = "active" if row["end_date"] >= date.today() else "expired"

    flags = []

    if pct_of_limit >= NEAR_LIMIT_THRESHOLD and days_since_start <= EARLY_CLAIM_WINDOW_DAYS:
        flags.append(
            f"Claim is {pct_of_limit*100:.0f}% of coverage limit and filed only "
            f"{days_since_start} day(s) after policy start - classic early large-claim pattern."
        )

    if row["incident_date"] > row["end_date"]:
        flags.append(
            f"Incident date ({row['incident_date']}) is after the policy's end date "
            f"({row['end_date']}) - policy had already lapsed."
        )

    # Deliberately NOT flagging "policy is expired now" on its own - see module
    # docstring. That check produced 67% false-positive flags in testing.

    if len(flags) >= 2:
        risk_level = "high"
    elif len(flags) == 1:
        risk_level = "medium"
    else:
        risk_level = "low"

    return {
        "claim_id": claim_id,
        "found": True,
        "risk_level": risk_level,
        "flags": flags,
        "claim_amount": float(row["claim_amount"]),
        "coverage_limit": float(row["coverage_limit"]),
        "pct_of_limit": round(pct_of_limit * 100, 1),
        "policy_status_live": policy_status_live,
        "days_since_policy_start": days_since_start,
    }


if __name__ == "__main__":
    test_ids = ["CLM300116", "CLM300186", "CLM300001", "CLM300002", "CLM300500"]
    for cid in test_ids:
        result = check_claim_fraud_risk(cid)
        print(f"\n{cid}:")
        for k, v in result.items():
            print(f"  {k}: {v}")
