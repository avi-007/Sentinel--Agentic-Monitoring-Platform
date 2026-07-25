# Sentinel

**Sentinel** is a real-time predictive monitoring platform: a synthetic infrastructure
fleet streams telemetry, an IsolationForest scores it for anomalies against a
threshold that adapts to recent behavior instead of a fixed cutoff, and an
autonomous GPT-4o agent investigates every triggered alert — pulling recent
metrics, logs, runbooks, and deploy history — before proposing a concrete fix.
Everything runs locally with `docker compose up`.

## Problem statement

Traditional monitoring pages a human for every metric that crosses a fixed
line, which either misses real incidents on noisy hosts or drowns quiet hosts
in false positives, and then leaves the actual diagnosis work — "why is this
happening and what do I do about it" — entirely to whoever's on call. Sentinel
is a small end-to-end demonstration of closing that loop: adaptive anomaly
detection that reduces false positives by design, followed by an agent that
does the first pass of root-cause investigation automatically and hands the
on-call engineer a concrete starting point instead of a bare metric spike.

## Architecture

```
generator          detector                          agent
(synthetic          (per-host IsolationForest          (multi-turn tool-calling
 telemetry)          + dynamic EWMA threshold)          investigation)
    |                     |                                  |
    v                     v                                  v
[Kafka: telemetry.raw] -> scores + writes           consumes alerts.triggered,
                           every event to             gathers context (metrics,
                           Postgres `metrics`,         logs, runbook, deploys),
                           publishes to                calls GPT-4o (or a free
                           [Kafka: alerts.triggered]   mock) in a tool-calling
                           when threshold crossed      loop, writes `agent_runs`
                                                        + updates `alerts.status`
                                                              |
                                                              v
                                            Grafana (single Postgres datasource)
                                            reads metrics/alerts/agent_runs directly
```

Kafka is purely the streaming backbone between generator→detector and
detector→agent. **Postgres is the single system of record** — there's no
Prometheus or Timescale in this stack; Grafana reads the same three tables the
services write to, which keeps the whole system easy to inspect with plain
SQL.

### Services

| Service | Role |
|---|---|
| `generator` | Simulates 6 hosts across 4 fake services (web/api/db/cache) — diurnal load shape + autocorrelated noise + a shared latent "stress" factor that makes latency and error rate rise together — with occasional spike/sustained/drift anomalies injected. Publishes to `telemetry.raw`. |
| `detector` | Consumes `telemetry.raw`, maintains a per-host `IsolationForest` (warm-up fit, periodic sliding-window retrain), scores each event, and applies a **dynamic EWMA threshold** instead of a static cutoff (see below). Writes every scored event to `metrics`; publishes to `alerts.triggered` when the threshold is crossed and the per-host cooldown allows it. |
| `agent` | Consumes `alerts.triggered`, runs a hand-written multi-turn tool-calling loop (mocked tools: recent metrics from Postgres, synthetic logs, a runbook, synthetic deploy history) against GPT-4o or a free deterministic mock, and persists the full transcript, root cause, and proposed fix to `agent_runs`. |
| `grafana` | Auto-provisioned (datasource + dashboard JSON checked into the repo, no manual UI setup) — live telemetry, anomaly score vs. threshold, and an alert feed with the agent's diagnosis. |

## Key design decisions

**Dynamic threshold, not a static cutoff.** A fixed score threshold assumes a
stationary anomaly-score distribution, but IsolationForest scores drift with
periodic retraining, legitimate diurnal load changes, and per-host baseline
noise — a noisy host trips a global cutoff constantly, a quiet host never
trips a loose one. Instead, per host, on `raw_score = -model.score_samples(x)`:

1. **EWMA control band** (Shewhart-style adaptive control limit):
   `μ_t = α·score_t + (1-α)·μ_{t-1}`, `σ_t` similarly over squared deviation,
   `threshold_t = μ_t + k·σ_t` (defaults `α=0.05`, `k=3.0`).
2. **Percentile floor guard**: `threshold_t = max(ewma_threshold_t, p95(recent
   scores))` — stops the band collapsing (and false-positive-flooding) during
   unusually calm stretches.
3. **Hysteresis/cooldown**: once an alert is published for a host, further
   publications are suppressed for 60s even if the score stays elevated, so one
   sustained incident doesn't become an alert storm. Every event is still
   scored and written to `metrics` regardless — only the alert publish is
   throttled.

See [`services/detector/app/dynamic_threshold.py`](services/detector/app/dynamic_threshold.py).

**Mock-by-default LLM.** `LLM_PROVIDER=mock` (the default) runs a deterministic
stand-in that walks the *same* tool-calling code path as real GPT-4o — same
tool schemas, same terminal `submit_diagnosis` call — so the entire pipeline is
demoable with zero cost and zero API key. Flip to `LLM_PROVIDER=openai` with an
`OPENAI_API_KEY` to use real GPT-4o.

**Hand-rolled tool loop, no agent framework.** [`services/agent/app/tool_loop.py`](services/agent/app/tool_loop.py)
is a plain `while` loop: call the model, execute whatever tools it requested,
feed results back, repeat until it calls the terminal `submit_diagnosis` tool
(not free-text parsing — a real tool call, which is reliable across both the
mock and real providers) or the turn cap is hit, at which point one final turn
forces `submit_diagnosis` so a structured result is always persisted.

**Package choices.** `confluent-kafka` (librdkafka bindings, the production
standard, ships a proper `AdminClient`) over `kafka-python` (stale) or
`aiokafka` (forces async onto simple tick/consume loops for no benefit here).
`psycopg` v3 with no ORM — three tables, mostly-append writes, and Grafana
queries them directly via raw SQL anyway, so the write path stays legible
against [`db/init/001_schema.sql`](db/init/001_schema.sql).

**Alert ownership.** The detector inserts the `alerts` row itself (status
`new`) before publishing to Kafka — it's the source of truth for "an alert
happened." The agent only ever `UPDATE`s that row's status
(`investigating` → `diagnosed`), which avoids any create/race ambiguity
between the two services.

## Running locally

Requires Docker Desktop (or another Docker daemon) running, and Docker Compose
v2.

```bash
git clone <this repo>   # or just cd into ~/sentinel
cd sentinel
cp .env.example .env    # defaults work out of the box, LLM_PROVIDER=mock
docker compose up --build -d
```

Then:

- `docker compose ps` — confirm `kafka-init` exited 0 and everything else is
  running/healthy.
- `docker compose logs -f generator detector agent` — watch telemetry flow,
  the detector warm up (~120 events/host, a few minutes of simulated time)
  and start scoring, and the agent pick up alerts as they fire.
- Open **http://localhost:3000** (`admin` / `admin` by default) — the Sentinel
  Overview dashboard is already provisioned: live telemetry, the anomaly score
  overlaid on its dynamic threshold, and the alert feed with the agent's
  proposed fixes. Refreshes every 5s.
- `./scripts/seed_check.sh` or `make psql` for a quick SQL sanity check.

Expect the first alerts (and therefore the first agent diagnoses) a few
minutes after startup — each host needs `DET_WARMUP_EVENTS` (120, by default)
telemetry events before its IsolationForest is fit and scoring begins.

To stop: `docker compose down` (add `-v` / `make clean` to also drop the
Postgres volume and start fresh).

### Using real GPT-4o

```bash
# in .env
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...

docker compose up -d --build agent   # or: make restart-agent
```

Real and mock-provider `agent_runs` rows coexist fine (`llm_provider` column
records which produced each one). GPT-4o calls are small (a handful of short
tool-calling turns per alert) — expect low-cents-per-alert territory at
default settings, but keep an eye on `GEN_ANOMALY_INJECTION_RATE` if you're
running it unattended, since every fired alert triggers a real API call.

## Repository structure

```
sentinel/
├── docker-compose.yml
├── common/                # shared lib: settings, Kafka/DB helpers, message schemas
├── services/
│   ├── generator/app/     # synthetic telemetry + anomaly injection
│   ├── detector/app/      # feature engineering, IsolationForest, dynamic threshold
│   └── agent/app/         # LLM client (mock/openai), tool loop, mocked tools
├── db/init/001_schema.sql # Postgres schema (hosts, metrics, alerts, agent_runs)
├── kafka/init/            # one-shot topic-creation job
├── grafana/               # provisioned datasource + dashboard JSON
└── scripts/seed_check.sh  # post-startup smoke test
```

## Configuration reference

All variables live in [`.env.example`](.env.example) with the same defaults
hardcoded into each service's `config.py` (so services also run standalone,
e.g. under tests, without a `.env` file). Highlights:

| Variable | Default | Meaning |
|---|---|---|
| `GEN_TIME_SCALE_FACTOR` | `48` | Compresses simulated time so a full diurnal cycle plays out in minutes, not 24h. |
| `GEN_ANOMALY_INJECTION_RATE` | `0.02` | Per-host, per-tick probability of starting a new injected anomaly. |
| `DET_WARMUP_EVENTS` | `120` | Events buffered per host before the first IsolationForest fit. |
| `DET_EWMA_ALPHA`, `DET_THRESHOLD_K` | `0.05`, `3.0` | Dynamic threshold band parameters. |
| `DET_ALERT_COOLDOWN_SECONDS` | `60` | Per-host suppression window between alert publications. |
| `LLM_PROVIDER` | `mock` | `mock` or `openai`. |
| `AGENT_MAX_TOOL_TURNS` | `6` | Tool-calling turns before the agent is forced to submit a diagnosis. |

## Limitations / what's simplified for a demo

- No auth or TLS anywhere (Grafana `admin/admin`, plaintext Kafka/Postgres) —
  local demo only.
- Single-broker Kafka, no replication (production would run ≥3 brokers, RF≥3).
- No Kubernetes; a single `docker-compose.yml`, one replica per service.
- `search_logs` and `get_deploy_history` are entirely synthetic — there's no
  real log store or CI/CD system behind them.
- IsolationForest retraining has no holdout validation or rollback; a fresh
  fit always replaces the previous model. The dynamic threshold is the actual
  guard against false positives, not the model boundary itself.
- Detector model state is in-memory only — a restart re-runs warm-up from
  scratch (no model persistence/registry).
- Plain JSON over Kafka, no schema registry — simpler to inspect at this
  scale, but wouldn't be the choice at larger fan-out.

## Possible extensions

- An evaluation harness comparing detected alerts against the generator's
  `injected_anomaly` ground-truth field (precision/recall over time).
- Multi-broker Kafka with real replication.
- A real log/metrics backend behind the agent's tools instead of synthetic
  fixtures.
- Model persistence (snapshot IsolationForest to disk/S3, versioned registry).
- Alerting integrations (Slack, PagerDuty) fed by `alerts.triggered`.
- Auth in front of Grafana/Postgres for anything beyond a local demo.

## License

MIT.
