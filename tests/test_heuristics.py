import pytest
from src.heuristics import evaluate_semantic_sanity


# ---- Heuristic 1: Cartesian product ----

def test_cartesian_product_heuristic():
    sql = "SELECT * FROM customers, orders, line_items;"
    results = [{"dummy": i} for i in range(1001)]  # > 1000 rows
    question = "List all orders"
    res = evaluate_semantic_sanity(sql, results, question)
    assert res["is_suspicious"] is True
    assert "unusually large" in res["reason"]


# ---- Heuristic 2: Empty result ----

def test_empty_entity_query_heuristic():
    """A genuine entity question with no filter that should plausibly have data."""
    sql = "SELECT * FROM customers WHERE region = 'NonExistent';"
    results = []
    question = "Show all customers from NonExistent region"
    res = evaluate_semantic_sanity(sql, results, question)
    assert res["is_suspicious"] is True
    assert "Query returned 0 rows" in res["reason"]


def test_legitimate_empty_existence_query():
    """A yes/no boolean existence question — empty is fine."""
    sql = "SELECT * FROM customers WHERE region = 'Atlantis';"
    results = []
    question = "Are there any customers from Atlantis?"
    res = evaluate_semantic_sanity(sql, results, question)
    assert res["is_suspicious"] is False
    assert res["reason"] is None


def test_legitimate_empty_negation_query_never():
    """Negation with 'never' — legitimately empty when all customers have orders."""
    sql = "SELECT * FROM customers c WHERE NOT EXISTS (SELECT 1 FROM orders o WHERE o.cust_id = c.customer_id)"
    results = []
    question = "Show all customers who have never placed an order"
    res = evaluate_semantic_sanity(sql, results, question)
    assert res["is_suspicious"] is False
    assert res["reason"] is None


def test_legitimate_empty_negation_query_without():
    """Negation with 'without' — legitimately empty result."""
    sql = "SELECT * FROM customers c LEFT JOIN orders o ON c.customer_id = o.cust_id WHERE o.id IS NULL"
    results = []
    question = "Find customers without any orders"
    res = evaluate_semantic_sanity(sql, results, question)
    assert res["is_suspicious"] is False
    assert res["reason"] is None


def test_legitimate_empty_threshold_query():
    """Threshold query ('more than 5') — legitimately empty when no data meets threshold."""
    sql = "SELECT c.customer_id, c.name FROM customers c JOIN orders o ON c.customer_id = o.cust_id GROUP BY c.customer_id, c.name HAVING COUNT(o.id) > 5"
    results = []
    question = "Which customers have placed more than 5 orders?"
    res = evaluate_semantic_sanity(sql, results, question)
    assert res["is_suspicious"] is False
    assert res["reason"] is None


def test_empty_entity_query_with_equals_filter_is_suspicious():
    """Entity question + empty result + normal '=' filter: -> suspicious."""
    sql = "SELECT * FROM customers WHERE region = 'New York'"
    results = []
    question = "Show me all customers in New York."
    res = evaluate_semantic_sanity(sql, results, question)
    assert res["is_suspicious"] is True
    assert "Query returned 0 rows" in res["reason"]


def test_empty_entity_query_with_ilike_filter_not_suspicious():
    """Entity question + empty result + ILIKE filter: -> NOT suspicious."""
    sql = "SELECT * FROM customers WHERE region ILIKE 'New York'"
    results = []
    question = "Show me all customers in New York."
    res = evaluate_semantic_sanity(sql, results, question)
    assert res["is_suspicious"] is False
    assert res["reason"] is None


# ---- Heuristic 3: Single NULL aggregate ----

def test_single_null_aggregation_no_where_suspicious():
    """Unconditional aggregate returning NULL IS suspicious — no WHERE clause."""
    sql = "SELECT SUM(total_amount) AS total FROM orders"
    results = [{"total": None}]
    question = "What is the total revenue?"
    res = evaluate_semantic_sanity(sql, results, question)
    assert res["is_suspicious"] is True
    assert "NULL aggregation value" in res["reason"]


def test_single_null_aggregation_with_where_not_suspicious():
    """Filtered aggregate returning NULL is NOT suspicious — filter may match 0 rows."""
    sql = "SELECT SUM(qty) AS total_quantity FROM line_items WHERE product_name = 'Mechanical Gaming Keyboard'"
    results = [{"total_quantity": None}]
    question = "Find total quantity of 'Mechanical Gaming Keyboard' sold"
    res = evaluate_semantic_sanity(sql, results, question)
    assert res["is_suspicious"] is False
    assert res["reason"] is None


def test_single_null_aggregation_with_where_date_not_suspicious():
    """Date-filtered aggregate returning NULL is not flagged — date may match 0 rows."""
    sql = "SELECT SUM(total_amount) AS total FROM orders WHERE order_date = '1900-01-01'"
    results = [{"total": None}]
    question = "What is the total revenue in 1900?"
    res = evaluate_semantic_sanity(sql, results, question)
    assert res["is_suspicious"] is False
    assert res["reason"] is None


def test_normal_null_containing_results():
    """Multi-row results with some NULL values in non-aggregate columns are fine."""
    sql = "SELECT customer_id, name, region FROM customers LIMIT 3;"
    results = [
        {"customer_id": 1, "name": "Alice", "region": "North"},
        {"customer_id": 2, "name": "Bob", "region": None},
        {"customer_id": 3, "name": "Charlie", "region": "South"}
    ]
    question = "List top 3 customers"
    res = evaluate_semantic_sanity(sql, results, question)
    assert res["is_suspicious"] is False
    assert res["reason"] is None
