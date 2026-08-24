up:
	docker compose up -d --build

down:
	docker compose down -v

logs:
	docker compose logs -f --tail=200

init-topics:
	docker compose exec redpanda rpk topic create assessment.submissions assessment.responses assessment.metrics assessment.deadletter || true

db-init:
	docker compose exec api alembic upgrade head

seed:
	docker compose exec -e PYTHONPATH=/app api python scripts/seed_template.py

ml-features:
	DATABASE_URL=postgresql+psycopg://assessment:assessment@localhost:5433/assessment \
	FEATURE_OUTPUT_PATH=ml/features/feature_frame.parquet \
	python -m ml.features.feature_pipeline

ml-features-trino:
	TRINO_URL=trino://trino@localhost:8080/demo \
	FEATURE_OUTPUT_PATH=ml/features/feature_frame.parquet \
	python -m ml.features.feature_pipeline --source trino

ml-labels:
	DATABASE_URL=postgresql+psycopg://assessment:assessment@localhost:5433/assessment \
	python -m ml.outcomes.labeled_outcomes

ml-relabel:
	DATABASE_URL=postgresql+psycopg://assessment:assessment@localhost:5433/assessment \
	python -m ml.outcomes.labeled_outcomes --incremental

ml-relabel-and-retrain:
	DATABASE_URL=postgresql+psycopg://assessment:assessment@localhost:5433/assessment \
	MLFLOW_TRACKING_URI=http://localhost:5000 \
	MLFLOW_S3_ENDPOINT_URL=http://localhost:9000 \
	AWS_ACCESS_KEY_ID=minioadmin \
	AWS_SECRET_ACCESS_KEY=minioadmin \
	python -m ml.outcomes.labeled_outcomes --incremental --retrain-threshold 5

ml-train:
	DATABASE_URL=postgresql+psycopg://assessment:assessment@localhost:5433/assessment \
	MLFLOW_TRACKING_URI=http://localhost:5000 \
	MLFLOW_S3_ENDPOINT_URL=http://localhost:9000 \
	AWS_ACCESS_KEY_ID=minioadmin \
	AWS_SECRET_ACCESS_KEY=minioadmin \
	python -m ml.training.train_readiness_model

ml-promote:
	MLFLOW_TRACKING_URI=http://localhost:5000 \
	python -m ml.promotion.promote

ml-rollback:
	MLFLOW_TRACKING_URI=http://localhost:5000 \
	python -m ml.promotion.rollback

ml-check:
	DATABASE_URL=postgresql+psycopg://assessment:assessment@localhost:5433/assessment \
	python -m ml.checks.label_quality

ml-drift:
	DATABASE_URL=postgresql+psycopg://assessment:assessment@localhost:5433/assessment \
	FEATURE_OUTPUT_PATH=ml/features/feature_frame.parquet \
	python -m ml.monitoring.drift

smoke:
	API_URL=http://localhost:8000 MLFLOW_URL=http://localhost:5000 \
	python -m ml.checks.smoke

seed-bulk:
	docker compose exec -e PYTHONPATH=/app api python scripts/seed_bulk.py

ml-all: seed-bulk ml-features ml-labels ml-check ml-train

test-ml:
	pytest ml/tests/ -v

dbt-run:
	cd analytics/dbt && dbt run

dbt-test:
	cd analytics/dbt && dbt test
