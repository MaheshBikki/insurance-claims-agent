"""
Milestone 7 (pulled forward) - Streamlit frontend for the claims agent.

This runs as a separate process from the FastAPI backend, on its own port.
It directly imports fraud_tool.py and settlement_tool.py (same codebase,
same server) rather than calling them over HTTP - simplest option for a
single-server portfolio deployment. In a larger production setup this
would call the FastAPI backend over the network instead.

The RAG/LLM chat tab is included but will show an error until the Bedrock
quota clears - that's left visible deliberately (not hidden) so anyone
testing this understands the RAG piece exists and why it's not live yet,
rather than silently omitting it.
"""
import streamlit as st
import psycopg2
import os

from fraud_tool import check_claim_fraud_risk
from settlement_tool import recommend_settlement


def get_random_claim_id() -> str:
    """Fetches one random claim_id from the database, so testers can explore
    beyond the 3 curated examples across all 5,000 seeded claims."""
    conn = psycopg2.connect(
        host=os.environ["DB_HOST"], port=os.environ.get("DB_PORT", "5432"),
        dbname=os.environ.get("DB_NAME", "claimsdb"), user=os.environ.get("DB_USER", "postgres"),
        password=os.environ["DB_PASSWORD"],
    )
    cur = conn.cursor()
    cur.execute("SELECT claim_id FROM claims ORDER BY RANDOM() LIMIT 1;")
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row[0] if row else ""

st.set_page_config(page_title="AI Claims Automation Agent", page_icon="🛡️", layout="centered")

st.title("🛡️ AI Claims & Underwriting Automation Agent")
st.caption(
    "Portfolio project - multi-agent claims pipeline (fraud detection + settlement "
    "recommendation) running on AWS. Synthetic data only, not a real insurer."
)

st.divider()

tab1, tab2 = st.tabs(["Check a Claim", "About this project"])

with tab1:
    st.subheader("Enter a Claim ID")
    st.write(
        "Dataset: 300 synthetic policies, 5,000 synthetic claims. "
        "Try one of these known example IDs, or enter your own:"
    )

    example_cols = st.columns(4)
    example_ids = {
        "CLM300116": "High risk (2 flags)",
        "CLM300186": "Medium risk (1 flag)",
        "CLM300500": "Low risk (auto-approved)",
    }
    if "claim_id_field" not in st.session_state:
        st.session_state["claim_id_field"] = ""

    for col, (cid, label) in zip(example_cols[:3], example_ids.items()):
        if col.button(f"{cid}\n{label}"):
            st.session_state["claim_id_field"] = cid

    if example_cols[3].button("🎲 Random Claim"):
        st.session_state["claim_id_field"] = get_random_claim_id()

    st.text_input(
        "Claim ID", key="claim_id_field", placeholder="e.g. CLM300116"
    )
    claim_id_input = st.session_state["claim_id_field"].strip().upper()

    check_clicked = st.button("Check Claim", type="primary")

    if check_clicked and claim_id_input:
        with st.spinner("Running fraud check and settlement calculation..."):
            fraud_result = check_claim_fraud_risk(claim_id_input)

        if not fraud_result["found"]:
            st.error(f"No claim found with ID '{claim_id_input}'.")
        else:
            settlement_result = recommend_settlement(claim_id_input)

            risk_colors = {"low": "green", "medium": "orange", "high": "red"}
            risk = fraud_result["risk_level"]

            st.markdown(f"### Results for `{claim_id_input}`")

            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**Fraud Risk Assessment**")
                st.markdown(f":{risk_colors[risk]}[**{risk.upper()} RISK**]")
                st.metric("Claim amount", f"₹{fraud_result['claim_amount']:,.0f}")
                st.metric("% of coverage limit", f"{fraud_result['pct_of_limit']}%")
                if fraud_result["flags"]:
                    st.markdown("**Flags raised:**")
                    for flag in fraud_result["flags"]:
                        st.markdown(f"- {flag}")
                else:
                    st.markdown("_No fraud flags raised._")

            with col2:
                st.markdown("**Settlement Recommendation**")
                decision = settlement_result["decision"]
                if decision == "approve":
                    st.success(f"DECISION: {decision.upper()}")
                else:
                    st.warning(f"DECISION: {decision.upper()}")
                st.metric("Payout amount", f"₹{settlement_result['payout_amount']:,.2f}")
                st.markdown("**Reasoning:**")
                st.markdown(f"_{settlement_result['reasoning']}_")

    elif check_clicked:
        st.warning("Please enter a claim ID first.")

with tab2:
    st.subheader("Architecture")
    st.markdown(
        """
        This project automates part of an insurance claims workflow using a
        multi-agent pipeline:

        1. **Intake Agent** *(pending Bedrock access)* - extracts structured
           claim data from free-text submissions using an LLM.
        2. **Policy Verification Agent (RAG)** *(pending Bedrock access)* -
           retrieves relevant policy clauses to check coverage.
        3. **Fraud/Anomaly Agent** *(live)* - rule-based + statistical checks
           against claim amount, timing, and policy validity.
        4. **Settlement Recommendation Agent** *(live)* - combines fraud risk
           with deterministic payout math to recommend approve/escalate/deny.

        **Stack:** AWS EC2 (Docker), RDS PostgreSQL with pgvector, Amazon
        Bedrock (Claude + Titan Embeddings), Streamlit frontend, FastAPI
        backend.

        **Status note:** Steps 1 and 2 require Amazon Bedrock model access,
        which is pending a quota approval from AWS at the time of this demo.
        Steps 3 and 4 are fully live and running against a synthetic dataset
        of 300 policies and 5,000 claims.
        """
    )
