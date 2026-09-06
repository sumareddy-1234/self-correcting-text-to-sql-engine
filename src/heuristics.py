import re


def is_existence_question(question: str) -> bool:
    """
    Checks if the question is asking for boolean existence (yes/no) rather than a list of entities.
    Also returns True for negation/threshold questions where an empty result is legitimately correct.
    """
    q_lower = question.lower()

    # Explicit boolean existence patterns
    existence_patterns = [
        r"\bare there any\b",
        r"\bdoes .* exist\b",
        r"\bis there an?\b",
        r"\bdo we have\b",
        r"\bany customers?\b",
        r"\bany orders?\b",
        r"\bexist\?\b",
        r"\bhas any\b",
    ]
    for pattern in existence_patterns:
        if re.search(pattern, q_lower):
            return True

    # Negation patterns: questions asking for entities that explicitly lack something.
    # A correctly executed negation query can legitimately return 0 rows.
    negation_patterns = [
        r"\bnever\b",            # "customers who never placed an order"
        r"\bwho have not\b",
        r"\bwho has not\b",
        r"\bwho hasn'?t\b",
        r"\bwho haven'?t\b",
        r"\bhave not\b",
        r"\bhas not\b",
        r"\bhaven'?t\b",
        r"\bhasn'?t\b",
        r"\bwithout\b",          # "customers without any orders"
        r"\bno orders?\b",
        r"\bnot placed\b",
        r"\bnever placed\b",
        r"\bnot ordered\b",
    ]
    for pattern in negation_patterns:
        if re.search(pattern, q_lower):
            return True

    # Threshold/comparative patterns: "more than N", "greater than N", "at least N".
    # If no data meets the threshold, 0 rows is a correct and legitimate answer.
    threshold_patterns = [
        r"\bmore than\b",
        r"\bgreater than\b",
        r"\bless than\b",
        r"\bfewer than\b",
        r"\bat least\b",
        r"\bat most\b",
        r"\bover \d+\b",
        r"\bunder \d+\b",
        r"\babove \d+\b",
        r"\bbelow \d+\b",
        r"\bexceeding\b",
    ]
    for pattern in threshold_patterns:
        if re.search(pattern, q_lower):
            return True

    return False


def is_entity_question(question: str) -> bool:
    """Checks if the question implies expecting entities or lists of data."""
    q_lower = question.lower()
    entity_keywords = [
        "who", "which", "list", "show", "top", "find", "get",
        "what are", "display", "fetch", "names of", "details of", "customers", "orders"
    ]
    return any(keyword in q_lower for keyword in entity_keywords)


def _sql_has_where_clause(sql: str) -> bool:
    """Returns True if the SQL has a WHERE clause (indicating a filtered aggregate)."""
    return bool(re.search(r"\bWHERE\b", sql, re.IGNORECASE))


def is_aggregation_query(sql: str, question: str) -> bool:
    """Checks if query or question represents an aggregate calculation."""
    sql_upper = sql.upper()
    agg_funcs = ["SUM(", "AVG(", "COUNT(", "MAX(", "MIN("]
    if any(func in sql_upper for func in agg_funcs):
        return True
    q_lower = question.lower()
    agg_keywords = ["total", "average", "avg", "count", "sum", "maximum", "minimum", "revenue", "spending"]
    return any(kw in q_lower for kw in agg_keywords)


def evaluate_semantic_sanity(sql: str, results: list, question: str) -> dict:
    """
    Evaluates executed SQL results against semantic heuristics.

    Returns dict with:
        is_suspicious (bool)
        reason (str | None)
    """
    if results is None:
        results = []

    # Heuristic 1: Massive / Cartesian Result (>1000 rows)
    if len(results) > 1000:
        return {
            "is_suspicious": True,
            "reason": f"Result set is unusually large ({len(results)} rows). Check for missing or incorrect JOIN conditions (Cartesian product)."
        }

    # Heuristic 2: Empty Result for Entity Questions
    # Conservative: only flag if the question genuinely implies entities should exist
    # AND it is not a negation, threshold, or existence/boolean question.
    if len(results) == 0:
        if is_entity_question(question) and not is_existence_question(question):
            if "ILIKE" not in sql.upper():
                return {
                    "is_suspicious": True,
                    "reason": "Query returned 0 rows, but the question implies entities exist. Check WHERE clause filters (date ranges, exact string matches, or case sensitivity)."
                }

    # Heuristic 3: Single NULL Aggregation Result
    # Conservative: only flag when there is NO WHERE clause.
    # If a WHERE clause is present, a NULL aggregate can be the legitimate answer
    # when no rows match the filter (e.g., a product that doesn't exist).
    if len(results) == 1:
        row = results[0]
        if isinstance(row, dict) and row:
            non_null_values = [v for v in row.values() if v is not None]
            if len(non_null_values) == 0 and is_aggregation_query(sql, question):
                # Only flag as suspicious if there is no WHERE clause.
                # A WHERE-filtered aggregate returning NULL is plausibly correct.
                if not _sql_has_where_clause(sql):
                    return {
                        "is_suspicious": True,
                        "reason": "Query returned a single row with NULL aggregation value. Check filter conditions or column names."
                    }

    return {
        "is_suspicious": False,
        "reason": None
    }
