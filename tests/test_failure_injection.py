import pytest
from src.agent import run_text_to_sql_pipeline


class MockLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.idx = 0

    def __call__(self, prompt, system_prompt=None):
        resp = self.responses[self.idx]
        self.idx = min(self.idx + 1, len(self.responses) - 1)
        return resp


def test_failure_injection_syntax(monkeypatch):
    """Verifies that syntax guardrail failures produce failure_type = 'syntax' and use syntax repair prompt."""
    prompts_received = []

    def mock_llm(prompt, system_prompt=None):
        prompts_received.append(prompt)
        if len(prompts_received) == 1:
            return "DELETE FROM customers;"  # Blocked by guardrail
        return "SELECT * FROM customers;"

    def mock_db(sql, db_config=None):
        return {"success": True, "results": [{"customer_id": 1}], "error": None}

    monkeypatch.setattr("src.agent.execute_query", mock_db)

    res = run_text_to_sql_pipeline("Show customers", llm_client=mock_llm)
    assert res["status"] == "success"
    assert res["iterations"] == 2
    assert res["repair_history"][0]["failure_type"] == "syntax"
    assert "[TYPED REPAIR: SYNTAX / GUARDRAIL ERROR]" in prompts_received[1]


def test_failure_injection_schema(monkeypatch):
    """Verifies that DB engine schema errors produce failure_type = 'schema' and use schema repair prompt."""
    prompts_received = []

    def mock_llm(prompt, system_prompt=None):
        prompts_received.append(prompt)
        if len(prompts_received) == 1:
            return "SELECT invalid_col FROM customers;"
        return "SELECT customer_id FROM customers;"

    def mock_db(sql, db_config=None):
        if "invalid_col" in sql:
            return {"success": False, "results": [], "error": "column customers.invalid_col does not exist"}
        return {"success": True, "results": [{"customer_id": 1}], "error": None}

    monkeypatch.setattr("src.agent.execute_query", mock_db)

    res = run_text_to_sql_pipeline("Show customer column", llm_client=mock_llm)
    assert res["status"] == "success"
    assert res["iterations"] == 2
    assert res["repair_history"][0]["failure_type"] == "schema"
    assert "[TYPED REPAIR: SCHEMA CATALOG ERROR]" in prompts_received[1]


def test_failure_injection_semantic(monkeypatch):
    """Verifies that semantic heuristic flags produce failure_type = 'semantic' and use semantic repair prompt."""
    prompts_received = []

    def mock_llm(prompt, system_prompt=None):
        prompts_received.append(prompt)
        if len(prompts_received) == 1:
            return "SELECT * FROM customers, orders, line_items;"  # Cartesian product
        return "SELECT c.name, o.id FROM customers c JOIN orders o ON c.customer_id = o.cust_id;"

    def mock_db(sql, db_config=None):
        if "line_items" in sql:
            return {"success": True, "results": [{"a": 1}] * 1005, "error": None}  # > 1000 rows
        return {"success": True, "results": [{"name": "Alice", "id": 10}], "error": None}

    monkeypatch.setattr("src.agent.execute_query", mock_db)

    res = run_text_to_sql_pipeline("Show customers and orders", llm_client=mock_llm)
    assert res["status"] == "success"
    assert res["iterations"] == 2
    assert res["repair_history"][0]["failure_type"] == "semantic"
    assert "[TYPED REPAIR: SEMANTIC SUSPICION ERROR]" in prompts_received[1]


def test_failure_injection_max_attempts(monkeypatch):
    """Verifies hard max 3 attempts limit when 3 consecutive errors occur."""
    def mock_llm(prompt, system_prompt=None):
        return "INVALID SYNTAX XYZ;"

    res = run_text_to_sql_pipeline("Impossible query", llm_client=mock_llm)
    assert res["status"] == "failed"
    assert res["iterations"] == 3
    assert len(res["repair_history"]) == 3
    for item in res["repair_history"]:
        assert item["failure_type"] == "syntax"
