import os
import json
import sys
from decimal import Decimal
from dotenv import load_dotenv

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.db import execute_query, get_db_config
from src.agent import run_text_to_sql_pipeline

load_dotenv()


def normalize_val(val):
    """Normalizes database field values for comparison."""
    if val is None:
        return None
    if isinstance(val, (int, float, Decimal)):
        return round(float(val), 4)
    return str(val).strip()


def normalize_row(row: dict) -> tuple:
    """Converts dict row into canonical sorted tuple."""
    return tuple((k, normalize_val(row[k])) for k in sorted(row.keys()))


def value_sort_key(val):
    """Sort key helper to allow sorting rows containing None values."""
    if val is None:
        return (0, "")
    if isinstance(val, (int, float, Decimal)):
        return (1, float(val))
    return (2, str(val))


def row_sort_key(row_tuple: tuple) -> tuple:
    return tuple((k, value_sort_key(v)) for k, v in row_tuple)


def compare_result_sets(gen_results: list, gold_results: list, sql_has_order_by: bool) -> bool:
    """
    Compares two database result sets.
    If sql_has_order_by is True, order matters. Otherwise, unordered set equality is checked.
    """
    if len(gen_results) != len(gold_results):
        return False
    if len(gen_results) == 0:
        return True

    if sql_has_order_by:
        for r_gen, r_gold in zip(gen_results, gold_results):
            if normalize_row(r_gen) != normalize_row(r_gold):
                return False
        return True
    else:
        norm_gen = sorted([normalize_row(r) for r in gen_results], key=row_sort_key)
        norm_gold = sorted([normalize_row(r) for r in gold_results], key=row_sort_key)
        return norm_gen == norm_gold


def run_evaluation():
    eval_file = os.path.join(os.path.dirname(__file__), "..", "data", "eval_set.json")
    out_file = os.path.join(os.path.dirname(__file__), "..", "results", "evaluation_metrics.json")

    if not os.path.exists(eval_file):
        raise FileNotFoundError(f"Evaluation set not found at {eval_file}")

    with open(eval_file, "r") as f:
        eval_data = json.load(f)

    db_config = get_db_config()

    configs = ["zero_shot", "syntax_schema_repair_only", "full_pipeline"]
    metrics_summary = {"configurations": {}}

    for config_name in configs:
        print(f"\n--- Running Evaluation Config: {config_name} ---")
        correct_count = 0
        total_iterations = 0
        total_schema_repairs = 0
        total_semantic_repairs = 0

        for item in eval_data:
            q_id = item["id"]
            question = item["question"]
            gold_sql = item["gold_sql"]

            # Execute gold SQL
            gold_res = execute_query(gold_sql, db_config=db_config)
            if not gold_res["success"]:
                print(f"Error executing gold SQL for Q{q_id}: {gold_res['error']}")
                gold_rows = []
            else:
                gold_rows = gold_res["results"]

            # Run agent pipeline
            agent_res = run_text_to_sql_pipeline(
                question=question,
                mode=config_name,
                db_config=db_config
            )

            total_iterations += agent_res["iterations"]

            # Count repairs by failure_type
            for rep in agent_res["repair_history"]:
                if rep["failure_type"] == "schema":
                    total_schema_repairs += 1
                elif rep["failure_type"] == "semantic":
                    total_semantic_repairs += 1

            if agent_res["status"] == "success":
                has_order_by = "ORDER BY" in gold_sql.upper()
                is_correct = compare_result_sets(agent_res["results"], gold_rows, has_order_by)
                if is_correct:
                    correct_count += 1

        accuracy_pct = round((correct_count / len(eval_data)) * 100, 2)
        avg_iterations = round(total_iterations / len(eval_data), 2)

        if config_name == "zero_shot":
            metrics_summary["configurations"][config_name] = {
                "accuracy_pct": accuracy_pct,
                "avg_iterations": avg_iterations
            }
        elif config_name == "syntax_schema_repair_only":
            metrics_summary["configurations"][config_name] = {
                "accuracy_pct": accuracy_pct,
                "avg_iterations": avg_iterations,
                "total_schema_repairs": total_schema_repairs
            }
        elif config_name == "full_pipeline":
            metrics_summary["configurations"][config_name] = {
                "accuracy_pct": accuracy_pct,
                "avg_iterations": avg_iterations,
                "total_semantic_repairs": total_semantic_repairs
            }

        print(f"Config '{config_name}': Accuracy = {accuracy_pct}%, Avg Iterations = {avg_iterations}")

    # Ensure output directory exists
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    with open(out_file, "w") as f:
        json.dump(metrics_summary, f, indent=2)

    print(f"\nSaved evaluation metrics to {out_file}")


if __name__ == "__main__":
    run_evaluation()
