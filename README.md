# Assessment Framework

Open-source assessment platform for collecting questionnaire responses, streaming events, building an analytics-ready lakehouse, and exposing observability dashboards.

## Architecture

- **React + Vite** UI for virtual questionnaire submission and review.
- **FastAPI** for form/session management, response capture, scoring hooks, and event emission.
- **Redpanda** for durable event streaming with Kafka-compatible APIs.
- **PySpark Structured Streaming** for Bronze/Silver/Gold processing.
- **Apache Iceberg + MinIO** for ML-ready analytical storage.
- **Trino** for SQL access across Iceberg tables.
- **dbt Core** for semantic models, marts, and tests.
- **Superset** for analytical dashboards.
- **Grafana + Prometheus + Loki + Tempo + OpenTelemetry Collector** for application and pipeline observability.

## Logical data flow

1. User opens the React questionnaire and submits an assessment.
2. FastAPI validates the payload, writes the operational record to Postgres, and publishes an event to Redpanda.
3. Spark Structured Streaming consumes Redpanda topics and writes append-only Iceberg Bronze tables.
4. Spark/SQL transforms produce Silver normalized response facts and Gold analytics aggregates.
5. dbt exposes curated marts for Superset and downstream ML feature engineering.
6. Grafana monitors the platform itself using metrics, traces, and logs.

## Quick start

```bash
cp .env.example .env
make up
make init-topics
make db-init
```

Then access:

- UI: http://localhost:5173
- API: http://localhost:8000/docs
- Superset: http://localhost:8088
- Grafana: http://localhost:3000
- Trino: http://localhost:8080
- Redpanda Console: http://localhost:8081

## Core topics

- `assessment.submissions`
- `assessment.responses`
- `assessment.metrics`
- `assessment.deadletter`

## Design principles

- Event-driven ingestion
- Contract-first schemas
- Medallion lakehouse layout
- Analytics engineering with tests and lineage
- OpenTelemetry-first observability
- ML-ready immutable response history
