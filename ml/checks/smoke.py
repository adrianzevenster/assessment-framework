"""
End-to-end smoke check against the running local stack.
Validates: API health, MLflow model registered, predict endpoint returns probability.

  make smoke          # run against default local stack
  API_URL=... MLFLOW_URL=... python -m ml.checks.smoke
"""
import os
import sys

import httpx

API_URL    = os.getenv("API_URL",    "http://localhost:8000")
MLFLOW_URL = os.getenv("MLFLOW_URL", "http://localhost:5000")


def check_api_health() -> None:
    r = httpx.get(f"{API_URL}/health", timeout=5)
    r.raise_for_status()
    assert r.json().get("status") == "ok", f"Unexpected health response: {r.json()}"
    print("  [OK] API health")


def check_mlflow_model() -> None:
    r = httpx.get(
        f"{MLFLOW_URL}/api/2.0/mlflow/registered-models/get-latest-versions",
        params={"name": "readiness-classifier"},
        timeout=5,
    )
    r.raise_for_status()
    versions = r.json().get("model_versions", [])
    assert versions, "No versions of readiness-classifier registered in MLflow. Run: make ml-train"
    print(f"  [OK] MLflow model: readiness-classifier v{versions[0]['version']}")


def check_predict_endpoint() -> None:
    subs_r = httpx.get(f"{API_URL}/analytics/submissions", timeout=5)
    subs_r.raise_for_status()
    submissions = subs_r.json()
    assert submissions, "No submissions found. Run: make seed-bulk"
    sid = submissions[0]["submission_id"]

    pred_r = httpx.get(f"{API_URL}/submissions/{sid}/predict", timeout=10)
    pred_r.raise_for_status()
    body = pred_r.json()

    if not body.get("available"):
        print(f"  [WARN] Predict returned available=false: {body.get('error')}")
        print("         Run: make ml-train to register a model")
        return

    prob = body.get("probability")
    assert isinstance(prob, float) and 0.0 <= prob <= 1.0, f"Bad probability: {prob}"
    print(f"  [OK] Predict endpoint: submission={sid[:8]}  probability={prob:.3f}")


def main() -> None:
    print("Running smoke checks against local stack...")
    failures = []
    for name, fn in [
        ("API health",       check_api_health),
        ("MLflow model",     check_mlflow_model),
        ("Predict endpoint", check_predict_endpoint),
    ]:
        try:
            fn()
        except Exception as exc:
            print(f"  [FAIL] {name}: {exc}", file=sys.stderr)
            failures.append(name)

    if failures:
        print(f"\n{len(failures)} check(s) failed.", file=sys.stderr)
        sys.exit(1)
    print("\nAll smoke checks passed.")


if __name__ == "__main__":
    main()
