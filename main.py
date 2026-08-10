"""
Milestone 1: minimal FastAPI service that calls Amazon Bedrock.
This is the foundation every later milestone (RAG, tools, agent orchestration) builds on.
"""
import json
import os
import boto3
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Insurance Claims Agent - Milestone 1")

# Bedrock client. On EC2 this automatically uses the instance's IAM role -
# no access keys needed or stored anywhere, which is the secure pattern.
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
bedrock = boto3.client("bedrock-runtime", region_name=AWS_REGION)

# Swap this if you request access to a different Bedrock model.
MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20241022-v2:0")


class AskRequest(BaseModel):
    question: str


class AskResponse(BaseModel):
    answer: str
    model_id: str


@app.get("/health")
def health():
    """Basic liveness check - useful once this is behind a load balancer or monitored."""
    return {"status": "ok"}


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest):
    """
    Sends a question straight to the LLM. No RAG, no tools yet -
    that's Milestone 2 and 3. This just proves the Bedrock connection works.
    """
    if not req.question or not req.question.strip():
        raise HTTPException(status_code=400, detail="question must not be empty")

    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 512,
        "messages": [
            {"role": "user", "content": req.question}
        ],
    }

    try:
        response = bedrock.invoke_model(
            modelId=MODEL_ID,
            body=json.dumps(body),
            contentType="application/json",
            accept="application/json",
        )
        result = json.loads(response["body"].read())
        answer = result["content"][0]["text"]
    except Exception as e:
        # In later milestones this becomes structured logging (CloudWatch) instead of a bare 500.
        raise HTTPException(status_code=500, detail=f"Bedrock call failed: {str(e)}")

    return AskResponse(answer=answer, model_id=MODEL_ID)
