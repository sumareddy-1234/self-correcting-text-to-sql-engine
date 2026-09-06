"""
Prompt templates for Initial Generation and Typed Repair Policies.
"""

FULL_SCHEMA_DDL = """
-- Database Schema Catalog (PostgreSQL Dialect)

-- 1. Table: customers
-- Note: Primary Key is customer_id (NOT id).
CREATE TABLE customers (
    customer_id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    region VARCHAR(50) -- NULLABLE column. Some customers have NULL region.
);

-- 2. Table: orders
-- Note: Foreign key to customers is cust_id (NOT customer_id).
-- Denormalized total_amount is stored here.
CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    cust_id INT REFERENCES customers(customer_id), -- FK mismatch: cust_id -> customers.customer_id
    order_date DATE NOT NULL,
    total_amount NUMERIC(10, 2) NOT NULL -- Pre-calculated sum of line_items
);

-- 3. Table: line_items
CREATE TABLE line_items (
    id SERIAL PRIMARY KEY,
    order_id INT REFERENCES orders(id), -- FK to orders.id
    product_name VARCHAR(100) NOT NULL,
    qty INT NOT NULL,
    unit_price NUMERIC(10, 2) NOT NULL
);
"""

SYSTEM_PROMPT = """You are an expert PostgreSQL Text-to-SQL engine.
Your task is to generate accurate, read-only standard PostgreSQL SQL queries based on the provided database schema catalog and user question.

CRITICAL INSTRUCTIONS:
1. Respond ONLY with executable PostgreSQL SQL code.
2. Do NOT wrap your SQL in markdown code fences like ```sql or ```.
3. Do NOT include any explanations, introduction, or conversational filler text.
4. Output ONLY standard SELECT statements. No DROP, DELETE, UPDATE, INSERT, ALTER, or TRUNCATE.
5. Pay strict attention to schema column names:
   - customers table primary key is 'customer_id'
   - orders table foreign key is 'cust_id' (references customers.customer_id)
   - orders table primary key is 'id'
   - line_items table foreign key is 'order_id' (references orders.id)
"""


def format_history(history: list) -> str:
    if not history:
        return "None."
    formatted = []
    for item in history:
        formatted.append(
            f"Attempt {item['attempt']}:\n"
            f"- SQL Attempted: {item['sql']}\n"
            f"- Failure Type: {item['failure_type']}\n"
            f"- Error Message / Reason: {item['error_message']}\n"
        )
    return "\n".join(formatted)


def build_initial_prompt(question: str) -> str:
    return f"""Database Schema Catalog:
{FULL_SCHEMA_DDL}

User Question: {question}

Generate the exact PostgreSQL SQL query to answer this question. Respond ONLY with raw SQL."""


def build_syntax_repair_prompt(question: str, malformed_sql: str, error_message: str, history: list) -> str:
    history_str = format_history(history)
    return f"""[TYPED REPAIR: SYNTAX / GUARDRAIL ERROR]

User Question: {question}

Database Schema Catalog:
{FULL_SCHEMA_DDL}

Previous Attempts History:
{history_str}

The SQL query generated in your last attempt was:
{malformed_sql}

Parsing / Syntax Error Message:
{error_message}

Instructions:
- The previous query failed AST / syntax validation or guardrail checks.
- Do NOT repeat the exact failed query or previous syntax mistakes.
- Ensure the output is valid, read-only PostgreSQL SELECT syntax.
- Respond ONLY with the corrected raw SQL query. No markdown formatting."""


def build_schema_repair_prompt(question: str, invalid_sql: str, error_message: str, history: list) -> str:
    history_str = format_history(history)
    return f"""[TYPED REPAIR: SCHEMA CATALOG ERROR]

User Question: {question}

Full Database Schema DDL Catalog:
{FULL_SCHEMA_DDL}

Previous Attempts History:
{history_str}

The SQL query generated in your last attempt was:
{invalid_sql}

PostgreSQL Database Engine Error:
{error_message}

Instructions:
- The database engine failed to execute the query due to a missing table, invalid column name, or wrong reference.
- Inspect the Full Database Schema DDL Catalog carefully:
  * Table 'customers' has primary key 'customer_id' (NOT 'id').
  * Table 'orders' has foreign key 'cust_id' (NOT 'customer_id').
  * Table 'orders' has primary key 'id'.
  * Table 'line_items' has foreign key 'order_id'.
- Fix column name mismatches and table join conditions.
- Respond ONLY with the corrected raw SQL query. No markdown formatting."""


def build_semantic_repair_prompt(question: str, executed_sql: str, heuristic_reason: str, sample_results: list, history: list) -> str:
    history_str = format_history(history)
    sample_str = str(sample_results[:3]) if sample_results else "[] (0 rows returned)"
    return f"""[TYPED REPAIR: SEMANTIC SUSPICION ERROR]

User Question: {question}

Database Schema Catalog:
{FULL_SCHEMA_DDL}

Previous Attempts History:
{history_str}

The executed SQL query was:
{executed_sql}

Result Set Sample (First 3 rows):
{sample_str}

Semantic Suspicion Flag:
{heuristic_reason}

Instructions:
- The SQL query executed without syntax or schema errors, but the resulting dataset is logically suspicious.
- If the result was empty (0 rows), verify WHERE clause filters (date ranges, string case sensitivity, unnecessary restrictive filters, or wrong JOIN types).
- If the result was a massive Cartesian product (>1000 rows), verify JOIN conditions between customers, orders, and line_items.
- If an aggregate total was NULL, check if line_items vs orders table was used properly or if NULL handling is needed.
- Respond ONLY with the corrected raw SQL query. No markdown formatting."""
