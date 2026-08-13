"""
Label quality gates. Run after ml-labels to catch imbalance and insufficient data.
Exits non-zero if any gate fails.

  make ml-check
"""
import os
import sys

from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://assessment:assessment@localhost:5432/assessment",
)

MIN_LABELED_ROWS = 10
MAX_MAJORITY_RATE = 0.95


def run_checks(engine) -> list[str]:
    failures: list[str] = []

    try:
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT COUNT(*), COALESCE(SUM(high_readiness), 0) FROM labeled_outcomes")
            ).fetchone()
    except Exception as exc:
        return [f"Cannot query labeled_outcomes: {exc}"]

    total, positives = int(row[0]), int(row[1])
    negatives = total - positives

    if total < MIN_LABELED_ROWS:
        failures.append(
            f"Too few labeled rows: {total} (min {MIN_LABELED_ROWS}). "
            "Run: make seed-bulk && make ml-labels"
        )

    if total > 0:
        majority_rate = max(positives, negatives) / total
        if majority_rate > MAX_MAJORITY_RATE:
            failures.append(
                f"Severe class imbalance: {positives} positive / {negatives} negative "
                f"(majority={majority_rate:.0%}). "
                "Consider adjusting the label rule in ml/features/extractor.py::compute_label."
            )

    return failures


def main() -> None:
    engine = create_engine(DATABASE_URL)
    failures = run_checks(engine)
    if failures:
        for msg in failures:
            print(f"FAIL  {msg}", file=sys.stderr)
        sys.exit(1)
    print("Label quality OK")


if __name__ == "__main__":
    main()
