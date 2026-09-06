import os
import openai
from dotenv import load_dotenv

from src.guardrails import validate_and_guard_sql, clean_sql_string
from src.db import execute_query
from src.heuristics import evaluate_semantic_sanity
from src.prompts import (
    SYSTEM_PROMPT,
    build_initial_prompt,
    build_syntax_repair_prompt,
    build_schema_repair_prompt,
    build_semantic_repair_prompt,
)

load_dotenv()


def call_llm(prompt: str, llm_client=None, system_prompt: str = SYSTEM_PROMPT) -> str:
    """Invokes LLM client (real Groq/OpenAI API or custom mock handler)."""
    if llm_client is not None:
        if callable(llm_client):
            return llm_client(prompt, system_prompt=system_prompt)
        elif hasattr(llm_client, "generate") and callable(getattr(llm_client, "generate")):
            return llm_client.generate(prompt, system_prompt=system_prompt)
        elif hasattr(llm_client, "chat") and hasattr(llm_client.chat, "completions"):
            model = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")
            response = llm_client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.0
            )
            return response.choices[0].message.content
        else:
            raise TypeError("Unsupported llm_client format.")

    # Default: Use Groq API (or OpenAI fallback if GROQ_API_KEY isn't set)
    groq_key = os.getenv("GROQ_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")
    api_key = groq_key or openai_key

    if not api_key:
        raise ValueError("Neither GROQ_API_KEY nor OPENAI_API_KEY environment variable is set.")

    base_url = os.getenv("GROQ_BASE_URL") or os.getenv("LLM_BASE_URL")
    if not base_url and groq_key:
        base_url = "https://api.groq.com/openai/v1"

    model = os.getenv("LLM_MODEL", "openai/gpt-oss-120b" if groq_key else "gpt-4o-mini")

    client_kwargs = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url

    client = openai.OpenAI(**client_kwargs)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        temperature=0.0
    )
    return response.choices[0].message.content


def run_text_to_sql_pipeline(
    question: str,
    llm_client=None,
    mode: str = "full_pipeline",
    db_config: dict = None,
    max_attempts: int = 3
) -> dict:
    """
    Executes the Text-to-SQL agent orchestration loop with typed self-correction.

    Parameters:
      - question (str): The natural language query.
      - llm_client: LLM caller or mock instance.
      - mode (str): 'full_pipeline', 'syntax_schema_repair_only', or 'zero_shot'.
      - db_config (dict): Optional PostgreSQL connection params.
      - max_attempts (int): Maximum total attempts (hard capped at 3 for repairs, 1 for zero_shot).

    Returns dict matching API schema:
      {
        "status": "success" | "failed",
        "final_sql": str,
        "results": list[dict],
        "iterations": int,
        "repair_history": [
           {"attempt": int, "failure_type": "syntax" | "schema" | "semantic", "error_message": str}
        ]
      }
    """
    if mode == "zero_shot":
        effective_max_attempts = 1
    else:
        effective_max_attempts = min(max_attempts, 3)

    repair_history = []
    history_context = []  # Detailed context passed to prompts

    last_attempted_sql = ""
    last_failure_type = None
    last_error_message = ""
    last_results = []

    for attempt in range(1, effective_max_attempts + 1):
        # 1. Build Prompt
        if attempt == 1:
            prompt = build_initial_prompt(question)
        else:
            if last_failure_type == "syntax":
                prompt = build_syntax_repair_prompt(
                    question, last_attempted_sql, last_error_message, history_context
                )
            elif last_failure_type == "schema":
                prompt = build_schema_repair_prompt(
                    question, last_attempted_sql, last_error_message, history_context
                )
            elif last_failure_type == "semantic":
                prompt = build_semantic_repair_prompt(
                    question, last_attempted_sql, last_error_message, last_results, history_context
                )
            else:
                prompt = build_initial_prompt(question)

        # 2. LLM Call
        try:
            raw_generated_sql = call_llm(prompt, llm_client=llm_client)
        except Exception as e:
            # LLM API error
            last_attempted_sql = ""
            last_failure_type = "syntax"
            last_error_message = f"LLM Generation Error: {str(e)}"
            repair_history.append({
                "attempt": attempt,
                "failure_type": "syntax",
                "error_message": last_error_message
            })
            history_context.append({
                "attempt": attempt,
                "sql": "N/A",
                "failure_type": "syntax",
                "error_message": last_error_message
            })
            continue

        clean_sql = clean_sql_string(raw_generated_sql)
        last_attempted_sql = clean_sql

        # 3. Guardrail / AST Syntax Check
        guardrail_res = validate_and_guard_sql(clean_sql)
        if not guardrail_res["is_valid"]:
            last_failure_type = "syntax"
            last_error_message = guardrail_res["error"]
            repair_history.append({
                "attempt": attempt,
                "failure_type": "syntax",
                "error_message": last_error_message
            })
            history_context.append({
                "attempt": attempt,
                "sql": clean_sql,
                "failure_type": "syntax",
                "error_message": last_error_message
            })
            continue

        valid_sql = guardrail_res["sql"]
        last_attempted_sql = valid_sql

        # 4. Schema Validation & Database Execution
        db_res = execute_query(valid_sql, db_config=db_config)
        if not db_res["success"]:
            last_failure_type = "schema"
            last_error_message = db_res["error"]
            repair_history.append({
                "attempt": attempt,
                "failure_type": "schema",
                "error_message": last_error_message
            })
            history_context.append({
                "attempt": attempt,
                "sql": valid_sql,
                "failure_type": "schema",
                "error_message": last_error_message
            })
            continue

        query_results = db_res["results"]
        last_results = query_results

        # 5. Semantic Sanity Check (Only enabled for 'full_pipeline')
        if mode == "full_pipeline":
            heuristic_res = evaluate_semantic_sanity(valid_sql, query_results, question)
            if heuristic_res["is_suspicious"]:
                last_failure_type = "semantic"
                last_error_message = heuristic_res["reason"]
                repair_history.append({
                    "attempt": attempt,
                    "failure_type": "semantic",
                    "error_message": last_error_message
                })
                history_context.append({
                    "attempt": attempt,
                    "sql": valid_sql,
                    "failure_type": "semantic",
                    "error_message": last_error_message
                })
                continue

        # 6. Success!
        return {
            "status": "success",
            "final_sql": valid_sql,
            "results": query_results,
            "iterations": attempt,
            "repair_history": repair_history
        }

    # All attempts exhausted
    return {
        "status": "failed",
        "final_sql": last_attempted_sql,
        "results": [],
        "iterations": len(repair_history) if repair_history else effective_max_attempts,
        "repair_history": repair_history
    }
