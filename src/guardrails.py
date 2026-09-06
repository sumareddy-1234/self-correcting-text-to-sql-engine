import re
import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError


def clean_sql_string(raw_sql: str) -> str:
    """Strips markdown code fences and extraneous whitespace."""
    if not raw_sql:
        return ""
    cleaned = raw_sql.strip()
    # Remove markdown ```sql ... ``` or ``` ... ```
    pattern = r"^```(?:sql)?\s*(.*?)\s*```$"
    match = re.search(pattern, cleaned, re.DOTALL | re.IGNORECASE)
    if match:
        cleaned = match.group(1).strip()
    # Strip any trailing semicolons or whitespace
    return cleaned


def validate_and_guard_sql(sql_string: str) -> dict:
    """
    Validates that a SQL string is safe and syntactically correct using sqlglot.
    Enforces read-only SELECT guardrails.

    Returns dict with keys:
      - is_valid (bool)
      - sql (str)
      - error (str | None)
      - failure_type (str | None): 'syntax' if invalid
    """
    cleaned_sql = clean_sql_string(sql_string)
    if not cleaned_sql:
        return {
            "is_valid": False,
            "sql": sql_string,
            "error": "Syntax Error: Empty SQL query provided.",
            "failure_type": "syntax"
        }

    # Reject multiple statements separated by semicolons
    statements = [s for s in cleaned_sql.split(';') if s.strip()]
    if len(statements) > 1:
        return {
            "is_valid": False,
            "sql": cleaned_sql,
            "error": "Security Guardrail Violation: Multiple SQL statements are not permitted.",
            "failure_type": "syntax"
        }

    try:
        ast = sqlglot.parse_one(cleaned_sql, read="postgres")
    except ParseError as e:
        return {
            "is_valid": False,
            "sql": cleaned_sql,
            "error": f"Syntax Error: {str(e)}",
            "failure_type": "syntax"
        }
    except Exception as e:
        return {
            "is_valid": False,
            "sql": cleaned_sql,
            "error": f"Syntax Error: Unable to parse query. {str(e)}",
            "failure_type": "syntax"
        }

    if ast is None:
        return {
            "is_valid": False,
            "sql": cleaned_sql,
            "error": "Syntax Error: Unparseable SQL expression.",
            "failure_type": "syntax"
        }

    # Forbidden DML/DDL types
    forbidden_types = (
        exp.Drop, exp.Delete, exp.Update, exp.Insert, exp.Alter,
        exp.TruncateTable, exp.Create, exp.Grant, exp.Revoke, exp.Command,
        exp.Merge
    )

    for node in ast.walk():
        if isinstance(node, forbidden_types):
            return {
                "is_valid": False,
                "sql": cleaned_sql,
                "error": f"Security Guardrail Violation: Destructive operation '{node.__class__.__name__}' is strictly prohibited. Only SELECT statements are permitted.",
                "failure_type": "syntax"
            }

    # Ensure statement is fundamentally a SELECT query (or a CTE terminating in a SELECT)
    if isinstance(ast, exp.With):
        if not isinstance(ast.this, exp.Select):
            return {
                "is_valid": False,
                "sql": cleaned_sql,
                "error": "Security Guardrail Violation: CTE statements must terminate in a SELECT query.",
                "failure_type": "syntax"
            }
    elif not isinstance(ast, exp.Select):
        return {
            "is_valid": False,
            "sql": cleaned_sql,
            "error": "Security Guardrail Violation: Only SELECT statements are permitted.",
            "failure_type": "syntax"
        }

    try:
        normalized_sql = ast.sql(dialect="postgres")
    except Exception:
        normalized_sql = cleaned_sql

    return {
        "is_valid": True,
        "sql": normalized_sql,
        "error": None,
        "failure_type": None
    }
