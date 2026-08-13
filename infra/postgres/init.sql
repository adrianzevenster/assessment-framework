CREATE SCHEMA IF NOT EXISTS public;
CREATE DATABASE superset OWNER assessment;

CREATE TABLE IF NOT EXISTS prediction_log (
    id             BIGSERIAL    PRIMARY KEY,
    submission_id  VARCHAR(26)  NOT NULL,
    model_name     TEXT         NOT NULL DEFAULT 'readiness-classifier',
    model_version  TEXT         NOT NULL,
    probability    REAL         NOT NULL,
    prediction     SMALLINT     NOT NULL,
    predicted_at   TIMESTAMP    NOT NULL DEFAULT now(),
    actual_label   SMALLINT
);
CREATE INDEX IF NOT EXISTS idx_prediction_log_submission_id ON prediction_log(submission_id);
CREATE INDEX IF NOT EXISTS idx_prediction_log_predicted_at  ON prediction_log(predicted_at);
