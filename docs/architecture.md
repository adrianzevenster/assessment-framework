# Assessment framework architecture

## Functional requirements

- Build configurable questionnaires.
- Persist every assessment, answer revision, and scoring event.
- Support virtual self-service submission.
- Expose analytics and observability.
- Keep raw data and curated features for downstream ML.

## Recommended bounded contexts

1. **Assessment authoring**: templates, sections, questions, answer constraints.
2. **Submission**: respondent sessions, answers, completion state, audit events.
3. **Streaming/processing**: event contracts, ingestion, schema validation, transformations.
4. **Analytics**: marts, KPIs, dashboards, cohort analysis.
5. **ML readiness**: feature tables, labeled outcomes, drift tracking, model feedback loops.

## Storage layers

### Operational Postgres
- Templates and question metadata
- Submission/session state
- Current answer snapshot for fast product reads

### Lakehouse (Iceberg on MinIO)
- Bronze raw events
- Silver conformed facts and dimensions
- Gold aggregates and feature-ready views

## Core analytical entities

- `fact_assessment_submission`
- `fact_assessment_response`
- `fact_question_metric`
- `dim_assessment_template`
- `dim_question`
- `dim_respondent`
- `dim_time`

## ML readiness guidelines

- Immutable event history
- Late-arriving update support
- PII separation/tokenization
- Slowly changing dimensions where needed
- Explicit label tables for supervised learning
- Feature definitions owned in dbt/Python
