import pytest
from src.guardrails import validate_and_guard_sql, clean_sql_string


def test_clean_sql_string():
    raw_markdown = "```sql\nSELECT * FROM customers;\n```"
    cleaned = clean_sql_string(raw_markdown)
    assert cleaned == "SELECT * FROM customers;"


def test_select_accepted():
    sql = "SELECT customer_id, name FROM customers WHERE region = 'West';"
    res = validate_and_guard_sql(sql)
    assert res["is_valid"] is True
    assert res["error"] is None
    assert res["failure_type"] is None


def test_select_cte_accepted():
    sql = "WITH regional_sales AS (SELECT cust_id, SUM(total_amount) as total FROM orders GROUP BY cust_id) SELECT * FROM regional_sales;"
    res = validate_and_guard_sql(sql)
    assert res["is_valid"] is True
    assert res["error"] is None


def test_drop_rejected():
    sql = "DROP TABLE customers;"
    res = validate_and_guard_sql(sql)
    assert res["is_valid"] is False
    assert "Security Guardrail Violation" in res["error"]
    assert res["failure_type"] == "syntax"


def test_delete_rejected():
    sql = "DELETE FROM orders WHERE id = 1;"
    res = validate_and_guard_sql(sql)
    assert res["is_valid"] is False
    assert res["failure_type"] == "syntax"


def test_update_rejected():
    sql = "UPDATE customers SET region = 'East' WHERE customer_id = 1;"
    res = validate_and_guard_sql(sql)
    assert res["is_valid"] is False
    assert res["failure_type"] == "syntax"


def test_insert_rejected():
    sql = "INSERT INTO customers (name, region) VALUES ('Hack', 'North');"
    res = validate_and_guard_sql(sql)
    assert res["is_valid"] is False
    assert res["failure_type"] == "syntax"


def test_alter_rejected():
    sql = "ALTER TABLE customers DROP COLUMN region;"
    res = validate_and_guard_sql(sql)
    assert res["is_valid"] is False
    assert res["failure_type"] == "syntax"


def test_truncate_rejected():
    sql = "TRUNCATE TABLE line_items;"
    res = validate_and_guard_sql(sql)
    assert res["is_valid"] is False
    assert res["failure_type"] == "syntax"


def test_multiple_statements_rejected():
    sql = "SELECT * FROM customers; DROP TABLE orders;"
    res = validate_and_guard_sql(sql)
    assert res["is_valid"] is False
    assert res["failure_type"] == "syntax"


def test_invalid_syntax_rejected():
    sql = "SELECT FROM WHERE customer_id =;"
    res = validate_and_guard_sql(sql)
    assert res["is_valid"] is False
    assert res["failure_type"] == "syntax"
