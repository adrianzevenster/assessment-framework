from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "assessment-api"
    database_url: str = "postgresql+psycopg://assessment:assessment@localhost:5432/assessment"
    redpanda_brokers: str = "localhost:19092"
    submission_topic: str = "assessment.submissions"
    response_topic: str = "assessment.responses"
    metrics_topic: str = "assessment.metrics"
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)


settings = Settings()
