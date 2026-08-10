"""
Milestone 2 - RAG ingestion pipeline.
Reads policy documents, splits them into chunks, embeds each chunk via
Bedrock Titan Embeddings, and stores the chunk + vector in pgvector.

Run this once (and again any time policy-docs/ changes) - NOT part of the
FastAPI app itself, since ingestion is a one-off/occasional job, not a
per-request operation.

Requires the Bedrock TPM quota to be approved before this will run
successfully - until then it will throw a ThrottlingException or
AccessDeniedException, same as the /ask endpoint does.
"""
import glob
import json
import os

import boto3
import psycopg2

AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")
EMBEDDING_MODEL_ID = "amazon.titan-embed-text-v2:0"

DB_HOST = os.environ["DB_HOST"]
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_NAME = os.environ.get("DB_NAME", "claimsdb")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ["DB_PASSWORD"]

CHUNK_SIZE = 500      # characters per chunk - deliberately small since these are short policy docs
CHUNK_OVERLAP = 100    # overlap so a clause split across a chunk boundary isn't lost entirely

bedrock = boto3.client("bedrock-runtime", region_name=AWS_REGION)


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP):
    """Simple fixed-size chunking with overlap. Good enough for short, well-structured
    policy docs - a real production system with longer/messier docs would likely need
    semantic chunking instead (splitting on headings/sections)."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + size
        chunks.append(text[start:end])
        start += size - overlap
    return [c.strip() for c in chunks if c.strip()]


def embed(text: str):
    """Calls Bedrock Titan Embeddings v2 and returns a 1024-dim vector."""
    body = json.dumps({"inputText": text})
    response = bedrock.invoke_model(
        modelId=EMBEDDING_MODEL_ID,
        body=body,
        contentType="application/json",
        accept="application/json",
    )
    result = json.loads(response["body"].read())
    return result["embedding"]


def infer_policy_type(filename: str) -> str:
    name = filename.lower()
    if "auto" in name:
        return "auto"
    if "health" in name:
        return "health"
    if "property" in name:
        return "property"
    return "unknown"


def main():
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD
    )
    cur = conn.cursor()

    # Clear any previous ingestion so re-running this script doesn't duplicate chunks
    cur.execute("DELETE FROM policy_chunks;")

    files = glob.glob("policy-docs/*.txt")
    print(f"Found {len(files)} policy documents to ingest.")

    total_chunks = 0
    for filepath in files:
        filename = os.path.basename(filepath)
        policy_type = infer_policy_type(filename)

        with open(filepath, "r") as f:
            text = f.read()

        chunks = chunk_text(text)
        print(f"  {filename}: {len(chunks)} chunks")

        for chunk in chunks:
            vector = embed(chunk)
            cur.execute(
                """
                INSERT INTO policy_chunks (source_file, policy_type, chunk_text, embedding)
                VALUES (%s, %s, %s, %s)
                """,
                (filename, policy_type, chunk, vector),
            )
            total_chunks += 1

    conn.commit()
    cur.close()
    conn.close()
    print(f"Done. Ingested {total_chunks} chunks total.")


if __name__ == "__main__":
    main()
