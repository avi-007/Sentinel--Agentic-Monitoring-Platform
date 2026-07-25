-- Sentinel schema. Mounted into postgres:/docker-entrypoint-initdb.d, runs once
-- on first container startup against a fresh pg-data volume.

CREATE TABLE IF NOT EXISTS hosts (
    host_id       TEXT PRIMARY KEY,
    service_name  TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS metrics (
    id                     BIGSERIAL PRIMARY KEY,
    event_id               UUID NOT NULL,
    host_id                TEXT NOT NULL REFERENCES hosts(host_id),
    service_name           TEXT NOT NULL,
    ts                     TIMESTAMPTZ NOT NULL,
    cpu_pct                DOUBLE PRECISION,
    mem_pct                DOUBLE PRECISION,
    latency_ms             DOUBLE PRECISION,
    error_rate_pct         DOUBLE PRECISION,
    features               JSONB,
    raw_score              DOUBLE PRECISION,
    ewma_mean              DOUBLE PRECISION,
    ewma_std               DOUBLE PRECISION,
    threshold              DOUBLE PRECISION,
    is_anomaly             BOOLEAN NOT NULL DEFAULT false,
    severity               TEXT,
    model_version          INTEGER,
    injected_anomaly_type  TEXT,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_metrics_host_ts ON metrics (host_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_metrics_ts ON metrics (ts DESC);

CREATE TABLE IF NOT EXISTS alerts (
    alert_id         UUID PRIMARY KEY,
    host_id          TEXT NOT NULL REFERENCES hosts(host_id),
    service_name     TEXT NOT NULL,
    triggered_at     TIMESTAMPTZ NOT NULL,
    raw_score        DOUBLE PRECISION NOT NULL,
    threshold        DOUBLE PRECISION NOT NULL,
    severity         TEXT NOT NULL,
    metric_snapshot  JSONB NOT NULL,
    metrics_id       BIGINT REFERENCES metrics(id),
    status           TEXT NOT NULL DEFAULT 'new', -- new|investigating|diagnosed|error
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_alerts_host_time ON alerts (host_id, triggered_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts (status);

CREATE TABLE IF NOT EXISTS agent_runs (
    run_id         UUID PRIMARY KEY,
    alert_id       UUID NOT NULL REFERENCES alerts(alert_id),
    llm_provider   TEXT NOT NULL, -- openai|mock
    model_name     TEXT,
    started_at     TIMESTAMPTZ NOT NULL,
    completed_at   TIMESTAMPTZ,
    turn_count     INTEGER,
    tool_calls     JSONB,         -- ordered [{tool, args, result}]
    transcript     JSONB NOT NULL, -- full raw chat message list
    root_cause     TEXT,
    proposed_fix   TEXT,
    confidence     DOUBLE PRECISION,
    status         TEXT NOT NULL DEFAULT 'completed', -- completed|failed|timeout
    error_message  TEXT,
    latency_ms     INTEGER,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_agent_runs_alert ON agent_runs (alert_id);
