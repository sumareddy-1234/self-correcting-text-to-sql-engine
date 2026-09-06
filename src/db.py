import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()


def get_db_config():
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", 5432)),
        "user": os.getenv("DB_USER", "postgres"),
        "password": os.getenv("DB_PASSWORD", "postgres"),
        "dbname": os.getenv("DB_NAME", "ecommerce_messy"),
    }


def execute_query(sql_string: str, db_config: dict = None) -> dict:
    """
    Executes a SQL query against PostgreSQL DB and returns dict with results or schema error.

    Returns dict:
        - success (bool)
        - results (list[dict])
        - error (str | None)
        - failure_type ('schema' | None)
    """
    if db_config is None:
        db_config = get_db_config()

    conn = None
    try:
        conn = psycopg2.connect(**db_config)
        conn.autocommit = True
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(sql_string)
            if cursor.description is not None:
                rows = cursor.fetchall()
                # Convert RealDictRow objects to standard python dicts
                results = [dict(row) for row in rows]
            else:
                results = []
        return {
            "success": True,
            "results": results,
            "error": None,
            "failure_type": None
        }
    except psycopg2.Error as e:
        error_msg = str(e).strip()
        return {
            "success": False,
            "results": [],
            "error": f"PostgreSQL Engine Error: {error_msg}",
            "failure_type": "schema"
        }
    except Exception as e:
        error_msg = str(e).strip()
        return {
            "success": False,
            "results": [],
            "error": f"Database Connection/Execution Error: {error_msg}",
            "failure_type": "schema"
        }
    finally:
        if conn:
            conn.close()
