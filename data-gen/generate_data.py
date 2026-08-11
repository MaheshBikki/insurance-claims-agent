"""
Generates a medium-scale synthetic dataset for the claims agent project:
- 300 policies across auto/health/property
- 5,000 claims against those policies

Design choices worth mentioning in an interview:
- ~4% of claims are deliberately "anomalous" (near coverage limit, filed within
  days of policy start, or against an expired/lapsed policy) - mirrors a
  realistic fraud-flag rate rather than an unrealistic 50/50 split.
- Uses only the Python standard library (random, csv, datetime) - no external
  dependencies needed to run this on a fresh EC2 instance.
- Outputs CSV rather than direct DB inserts, so it can be bulk-loaded with
  PostgreSQL's COPY command - much faster than row-by-row INSERTs at this
  volume, and a legitimate talking point on data-loading strategy.

Usage: python3 generate_data.py
Produces: policies.csv, claims.csv in the current directory.
"""
import csv
import random
from datetime import date, timedelta

random.seed(42)  # reproducible dataset - same data every run, useful for demos

POLICY_TYPES = ["auto", "health", "property"]
FIRST_NAMES = ["Rahul", "Priya", "Amit", "Sneha", "Karan", "Anita", "Vikram", "Neha",
               "Arjun", "Divya", "Rohan", "Pooja", "Sanjay", "Meera", "Aditya", "Kavya",
               "Suresh", "Ritu", "Manoj", "Anjali"]
LAST_NAMES = ["Sharma", "Nair", "Verma", "Reddy", "Mehta", "Iyer", "Gupta", "Rao",
              "Patel", "Singh", "Kumar", "Joshi", "Chatterjee", "Desai", "Pillai"]

INCIDENT_TYPES = {
    "auto": ["collision", "theft", "fire_damage", "third_party_liability"],
    "health": ["hospitalization", "surgery", "diagnostic", "emergency_care"],
    "property": ["fire_damage", "flood_damage", "burglary", "storm_damage"],
}

COVERAGE_RANGES = {
    "auto": (150000, 500000),
    "health": (200000, 1000000),
    "property": (500000, 2000000),
}

random_start = date(2024, 1, 1)
random_end = date(2026, 6, 30)


def random_date(start: date, end: date) -> date:
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, delta))


def gen_policies(n=300):
    policies = []
    for i in range(1, n + 1):
        policy_id = f"POL2{i:04d}"
        name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
        ptype = random.choice(POLICY_TYPES)
        low, high = COVERAGE_RANGES[ptype]
        coverage_limit = round(random.randint(low, high), -3)
        deductible = round(coverage_limit * random.uniform(0.01, 0.05), -2)
        start_date = random_date(random_start, date(2026, 4, 30))
        term_days = 365
        end_date = start_date + timedelta(days=term_days)
        status = "active" if end_date >= date(2026, 8, 10) else "expired"
        policies.append({
            "policy_id": policy_id,
            "policyholder_name": name,
            "policy_type": ptype,
            "coverage_limit": coverage_limit,
            "deductible": deductible,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "status": status,
        })
    return policies


def gen_claims(policies, n=5000):
    claims = []
    anomaly_count = 0
    target_anomaly_rate = 0.04

    for i in range(1, n + 1):
        claim_id = f"CLM3{i:05d}"
        policy = random.choice(policies)
        ptype = policy["policy_type"]
        incident_type = random.choice(INCIDENT_TYPES[ptype])
        coverage_limit = policy["coverage_limit"]
        policy_start = date.fromisoformat(policy["start_date"])
        policy_end = date.fromisoformat(policy["end_date"])

        make_anomaly = (anomaly_count / n) < target_anomaly_rate and random.random() < 0.06

        if make_anomaly:
            anomaly_type = random.choice(["near_limit_early", "post_expiry"])
            if anomaly_type == "near_limit_early":
                incident_date = policy_start + timedelta(days=random.randint(1, 6))
                claim_amount = round(coverage_limit * random.uniform(0.9, 1.0), -2)
            else:
                incident_date = policy_end + timedelta(days=random.randint(1, 60))
                claim_amount = round(coverage_limit * random.uniform(0.3, 0.8), -2)
            anomaly_count += 1
        else:
            latest_possible = min(policy_end, date(2026, 8, 9))
            if latest_possible <= policy_start:
                incident_date = policy_start
            else:
                incident_date = random_date(policy_start, latest_possible)
            claim_amount = round(coverage_limit * random.uniform(0.02, 0.6), -2)

        description = f"{incident_type.replace('_', ' ').title()} incident reported for {ptype} policy."

        claims.append({
            "claim_id": claim_id,
            "policy_id": policy["policy_id"],
            "claimant_name": policy["policyholder_name"],
            "incident_type": incident_type,
            "incident_date": incident_date.isoformat(),
            "claim_amount": claim_amount,
            "description": description,
            "status": "submitted",
        })

    return claims, anomaly_count


def write_csv(filename, rows, fieldnames):
    with open(filename, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    policies = gen_policies(300)
    claims, anomaly_count = gen_claims(policies, 5000)

    write_csv("policies.csv", policies,
              ["policy_id", "policyholder_name", "policy_type", "coverage_limit",
               "deductible", "start_date", "end_date", "status"])
    write_csv("claims.csv", claims,
              ["claim_id", "policy_id", "claimant_name", "incident_type",
               "incident_date", "claim_amount", "description", "status"])

    print(f"Generated {len(policies)} policies -> policies.csv")
    print(f"Generated {len(claims)} claims -> claims.csv")
    print(f"  Deliberately anomalous claims: {anomaly_count} ({anomaly_count/len(claims)*100:.1f}%)")


if __name__ == "__main__":
    main()
