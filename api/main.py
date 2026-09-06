import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

from src.agent import run_text_to_sql_pipeline

app = FastAPI(
    title="Self-Correcting Text-to-SQL Engine",
    description="A production-grade Text-to-SQL engine with AST guardrails, catalog validation, and typed self-correction.",
    version="1.0.0"
)


class QueryRequest(BaseModel):
    question: str = Field(..., description="Natural language question to translate into SQL and execute.")


class RepairHistoryItem(BaseModel):
    attempt: int
    failure_type: str = Field(..., description="'syntax', 'schema', or 'semantic'")
    error_message: str


class QueryResponse(BaseModel):
    status: str = Field(..., description="'success' or 'failed'")
    final_sql: str
    results: List[Dict[str, Any]]
    iterations: int
    repair_history: List[RepairHistoryItem]


@app.get("/health")
def health_check():
    """Healthcheck endpoint for container orchestrators."""
    return {"status": "healthy"}


@app.post("/api/query", response_model=QueryResponse)
def query_endpoint(request: QueryRequest):
    """
    Translates a natural language question into SQL, executes it, and performs typed repairs if necessary.
    """
    if not request.question or not request.question.strip():
        raise HTTPException(status_code=400, detail="Question string cannot be empty.")

    try:
        response_dict = run_text_to_sql_pipeline(request.question, mode="full_pipeline")
        return QueryResponse(**response_dict)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")
