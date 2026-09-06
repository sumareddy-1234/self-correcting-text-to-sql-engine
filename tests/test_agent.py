import pytest
from unittest.mock import MagicMock
from src.agent import run_text_to_sql_pipeline


class MockLLM:
    def __init__(self, sql_sequence):
        self.sql_sequence = list(sql_sequence)
        self.call_count = 0

    def __call__(self, prompt, system_prompt=None):
        sql = self.sql_sequence[self.call_count]
        self.call_count += 1
        return sql


def test_immediate_success(monkeypatch):
    mock_llm = MockLLM(["SELECT * FROM customers;"])
    
    # Mock db execution
    def mock_db(sql, db_config=None):
        return {"success": True, "results": [{"customer_id": 1, "name": "Alice"}], "error": None}

    monkeypatch.setattr("src.agent.execute_query", mock_db)

    res = run_text_to_sql_pipeline("List customers", llm_client=mock_llm)
    assert res["status"] == "success"
    assert res["iterations"] == 1
    assert len(res["repair_history"]) == 0


def test_syntax_failure_then_success(monkeypatch):
    mock_llm = MockLLM(["INVALID SQL SYNTAX", "SELECT * FROM customers;"])

    def mock_db(sql, db_config=None):
        return {"success": True, "results": [{"customer_id": 1}], "error": None}

    monkeypatch.setattr("src.agent.execute_query", mock_db)

    res = run_text_to_sql_pipeline("List customers", llm_client=mock_llm)
    assert res["status"] == "success"
    assert res["iterations"] == 2
    assert len(res["repair_history"]) == 1
    assert res["repair_history"][0]["failure_type"] == "syntax"


def test_schema_failure_then_success(monkeypatch):
    mock_llm = MockLLM(["SELECT customer_id FROM orders;", "SELECT cust_id FROM orders;"])

    call_counts = {"count": 0}

    def mock_db(sql, db_config=None):
        call_counts["count"] += 1
        if call_counts["count"] == 1:
            return {"success": False, "results": [], "error": "column orders.customer_id does not exist"}
        return {"success": True, "results": [{"cust_id": 1}], "error": None}

    monkeypatch.setattr("src.agent.execute_query", mock_db)

    res = run_text_to_sql_pipeline("Get order cust_ids", llm_client=mock_llm)
    assert res["status"] == "success"
    assert res["iterations"] == 2
    assert len(res["repair_history"]) == 1
    assert res["repair_history"][0]["failure_type"] == "schema"


def test_semantic_failure_then_success(monkeypatch):
    mock_llm = MockLLM(["SELECT * FROM customers WHERE region = 'Wrong';", "SELECT * FROM customers WHERE region = 'West';"])

    call_counts = {"count": 0}

    def mock_db(sql, db_config=None):
        call_counts["count"] += 1
        if call_counts["count"] == 1:
            return {"success": True, "results": [], "error": None}  # Empty entity result -> semantic error
        return {"success": True, "results": [{"customer_id": 1, "name": "Alice", "region": "West"}], "error": None}

    monkeypatch.setattr("src.agent.execute_query", mock_db)

    res = run_text_to_sql_pipeline("List customers in West region", llm_client=mock_llm)
    assert res["status"] == "success"
    assert res["iterations"] == 2
    assert len(res["repair_history"]) == 1
    assert res["repair_history"][0]["failure_type"] == "semantic"


def test_max_three_attempts_failure(monkeypatch):
    mock_llm = MockLLM(["DROP TABLE customers;", "DROP TABLE orders;", "DROP TABLE line_items;", "SELECT 1;"])

    res = run_text_to_sql_pipeline("Malicious prompt", llm_client=mock_llm)
    assert res["status"] == "failed"
    assert res["iterations"] == 3
    assert len(res["repair_history"]) == 3
    assert mock_llm.call_count == 3  # Never attempts 4th call
