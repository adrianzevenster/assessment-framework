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
	docker compose exec api python scripts/seed_template.py
