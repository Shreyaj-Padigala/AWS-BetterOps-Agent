# Implementation Plan

Living document. Each phase lists concrete tasks, the definition of done, and the
dependencies it introduces. Phases are built in order; directories are created when
their phase begins, not in advance.

Legend: `[x]` done · `[ ]` not started · `[~]` in progress

---

## Phase 0 — Architecture and project setup  ✅ Complete

- [x] `README.md` — product summary, stack, local setup, layout
- [x] `architecture.md` — topology, layering, data model, agents, MCP, RAG, caching, async, evaluation, decision log
- [x] `implementation_plan.md` — this file
- [x] `docker-compose.yml` — PostgreSQL + pgvector, Redis, LocalStack, app, worker
- [x] `.env.example` — every configuration variable, no real secrets
- [x] `.gitignore`
- [x] `requirements.txt` scoped to Phases 0–1 only

**Done when:** a new contributor can read the two design docs and understand the whole
system before opening any Python file.

---

## Phase 1 — Core Flask application  ✅ Complete

Goal: register, log in, create a project, create and view incidents. No AI.

- [x] `config.py` — environment-driven config, cookie/security defaults per environment
- [x] `app.py` — application factory, blueprint registration, error handlers, dev entrypoint
- [x] `database/db.py` — engine, session factory, request-scoped session
- [x] `database/models.py` — `User`, `Organization`, `OrganizationMember`, `Project`, `Incident`
- [x] `migrations/` — Alembic environment + initial revision
- [x] `repositories/` — user, organization, project, incident
- [x] `services/` — auth, project, incident (+ authorisation and tenancy enforcement)
- [x] `schemas/` — Pydantic request models and serialisers
- [x] `middleware/auth_middleware.py` — JWT cookie issue/verify, `@login_required`, request context
- [x] `middleware/request_logging.py` — request id, timing, structured log line
- [x] `errors.py` — `ApiError` hierarchy and the JSON error contract
- [x] `routes/` — `auth`, `project`, `incident`, plus page routes
- [x] `templates/` + `static/` — login, register, dashboard, projects, project detail, incidents, incident detail
- [x] `tests/` — auth, projects, incidents, tenancy isolation, validation, page routes

**Verified:**

- `pytest` — 69 passed (auth, projects, incidents, tenancy isolation, pages, config).
- `alembic upgrade head`, `alembic downgrade base`, and `alembic check` (no model drift).
- Live server smoke test: register → session cookie (`HttpOnly`, `SameSite=Strict`) →
  create project → create incident → dashboard counters → status transition sets
  `resolved_at` → status filtering → validation error contract → 401 when signed out →
  every page and static asset served → anonymous pages redirect to `/login` → logout
  invalidates the session. No errors in the server log.

**Not yet verified:** the run above used SQLite, because neither Docker nor the local
PostgreSQL service could be started in the build environment (the service needs
elevation). Run `alembic upgrade head` and the smoke flow once against PostgreSQL before
starting Phase 2 — the schema uses no PostgreSQL-specific types, so no code change is
expected.

**Deliberately deferred:** Redis, rate limiting, integrations, investigations, any
Bedrock call.

---

## Phase 2 — Redis, caching, backend hardening  ✅ Complete

- [x] `cache/backends.py` — one narrow interface with `RedisBackend`, `MemoryBackend`, `NullBackend`
- [x] `cache/redis_client.py` — process-wide backend, connection pool, socket timeouts, health check
- [x] `cache/cache_service.py` — cache-aside helpers, versioned namespaced keys, configurable TTLs, graceful degradation
- [x] `cache/metrics.py` — hit / miss / error / invalidation counters
- [x] Cache incident reads; invalidate after commit on write
- [x] `middleware/rate_limit.py` — fixed window per user per route class, `429` + `Retry-After`, per-IP limit on auth endpoints, fail-open
- [x] `logging_config.py` — JSON formatter with `request_id` / `user_id` / `organization_id` / `duration_ms` / `status`, sensitive-field redaction
- [x] `GET /api/system/cache` and cache status in `/healthz`
- [x] Tests: keys, hit, miss, TTL expiry, invalidation, namespace invalidation, undecodable entries, Redis-down fallback, rate-limit rejection and scope, window reset, log shape and redaction

**Verified:** 121 tests pass. Live run confirmed hit rate 0.5 across two reads,
invalidation on update, `429` with `Retry-After` after the budget was spent, pages
unaffected by API limits, and JSON log lines carrying tenant context.

**New dependencies:** `redis`, `fakeredis` (tests only)

**Deferred to the phase that needs it:** GitHub/CloudWatch/RAG cache namespaces (Phases
4–7), the `jti` denylist for immediate logout, and the distributed investigation lock
(Phase 9).

---

## Phase 3 — Amazon Bedrock / Nova integration

- [ ] `llm/nova_client.py` — Bedrock Converse wrapper, retries, timeouts, token accounting
- [ ] `llm/prompts.py` — versioned system prompts
- [ ] `llm/schemas.py` — Pydantic output schemas
- [ ] `agents/base_agent.py` — agent loop, budgets, structured-output parsing, one schema-repair retry
- [ ] `agents/triage_agent.py` — first real agent, no tools
- [ ] Model config centralised in `config.py`; no model id elsewhere
- [ ] Tests: schema validation, budget enforcement, repair retry, mocked Bedrock

**New dependencies:** `boto3`

---

## Phase 4 — MCP infrastructure + GitHub

- [ ] MCP server/client scaffolding and tool-registration pattern
- [ ] `mcp_servers/github_server/` — `get_recent_commits`, `get_commit`, `get_commit_diff`, `get_file`, `search_code`, `get_file_history`, `get_pull_request`
- [ ] `mcp_clients/github_client.py`
- [ ] `agents/code_agent.py`
- [ ] `tool_calls` table + auditing of every invocation
- [ ] Verify the full path: Nova → tool selection → MCP → GitHub → structured evidence

---

## Phase 5 — AWS Observability MCP

- [ ] `mcp_servers/aws_server/` — `search_logs`, `get_error_count`, `get_service_metrics`, `get_latency_metrics`, `get_recent_exceptions`, `get_ecs_service_health`, `get_lambda_errors`
- [ ] `agents/observability_agent.py`
- [ ] Cross-account `AssumeRole` with external id
- [ ] Deployment MCP + `agents/deployment_agent.py`

---

## Phase 6 — PostgreSQL diagnostic MCP

- [ ] Read-only enforcement: statement allowlist, read-only transaction, `statement_timeout`, row cap
- [ ] Tools: `get_schema`, `get_table_stats`, `get_connection_stats`, `get_slow_queries`, `get_indexes`, `explain_query`, `get_lock_stats`
- [ ] `agents/database_agent.py`
- [ ] Tests proving `INSERT/UPDATE/DELETE/DROP/ALTER/TRUNCATE/CREATE` are rejected

---

## Phase 7 — RAG

- [ ] S3 upload endpoint + `documents` / `document_chunks` tables + pgvector
- [ ] `rag/ingestion.py`, `rag/chunking.py`, `rag/embeddings.py` (Titan V2), `rag/retrieval.py`
- [ ] Knowledge MCP + `agents/knowledge_agent.py`
- [ ] Tenant-filtered retrieval enforced in SQL
- [ ] Retrieval-quality test set

---

## Phase 8 — Full orchestration

- [ ] `orchestration/orchestrator.py`, `investigation_state.py`, `agent_registry.py`
- [ ] Concurrent specialist execution with per-agent deadlines
- [ ] Evidence aggregation + `agents/root_cause_agent.py`
- [ ] Evidence-ID validation (reject fabricated citations)
- [ ] `unavailable_sources` propagation and confidence adjustment

---

## Phase 9 — SQS + workers

- [ ] `workers/investigation_worker.py`, SQS producer/consumer, LocalStack locally
- [ ] `202 Accepted` investigate endpoint, status polling endpoint
- [ ] Idempotency via Redis lock + active-investigation check
- [ ] Retries, visibility timeout, dead-letter queue

---

## Phase 10 — Evidence graph

- [ ] `evidence_nodes` / `evidence_edges` tables and relationship types
- [ ] Graph construction during analysis
- [ ] `GET /api/investigations/{id}/graph` + frontend visualisation and timeline

---

## Phase 11 — Fix Agent

- [ ] `agents/fix_agent.py` — patch, explanation, expected behaviour change, validation plan
- [ ] Diff rendering in the UI. No deployment.

---

## Phase 12 — Remediation sandbox

- [ ] Docker-isolated execution locally; CodeBuild / isolated ECS in AWS
- [ ] Unit + integration tests, lint, static analysis, benchmark
- [ ] Before/after metrics persisted and displayed

---

## Phase 13 — Pull request workflow

- [ ] Human approval gate → branch → commit → PR. Never auto-merge.

---

## Phase 14 — Incident simulator

- [ ] Demo app (frontend, checkout service, order service, PostgreSQL, external-api mock)
- [ ] Eight failure scenarios with ground truth
- [ ] `simulator/runner.py`, `simulator/ground_truth.py`

---

## Phase 15 — Evaluation platform

- [ ] Deterministic category scoring; optional LLM judge as a secondary metric
- [ ] Accuracy, latency, tool calls, LLM calls, tokens, cost, cache hit rate, unsupported-claim rate
- [ ] Configuration comparison (single agent / multi-agent / +RAG / +MCP)
- [ ] Evaluation dashboard

---

## Phase 16 — AWS deployment

- [ ] Dockerfile, ECS Fargate web + worker services, ALB, Route 53
- [ ] RDS PostgreSQL + pgvector, ElastiCache Redis, S3, SQS, Secrets Manager
- [ ] Least-privilege IAM, CloudWatch logs/metrics/alarms
- [ ] CI/CD pipeline

---

## Dependency introduction schedule

| Phase | Added |
|---|---|
| 0–1 | `flask`, `sqlalchemy`, `alembic`, `psycopg[binary]`, `pydantic[email]`, `pyjwt`, `python-dotenv`, `pytest` |
| 2 | `redis`, `fakeredis` (tests) |
| 3 | `boto3` |
| 4 | `mcp`, `httpx` |
| 7 | `pgvector`, `pypdf`, `boto3` (S3) |
| 12 | `docker` |
| 16 | `gunicorn` |

Nothing is installed before the phase that needs it.

---

## Current position

**Phases 0, 1 and 2 are complete.** The application runs, all 121 tests pass, migrations
apply and reverse cleanly, and the layering rules in `architecture.md` §4 hold.

**Outstanding environment checks** (neither is a code change, both need infrastructure
that could not be started in the build environment):

- Run the app and migrations against **PostgreSQL** rather than SQLite.
- Run it against a real **Redis** server (`docker compose up -d redis`, then
  `CACHE_BACKEND=redis`). `RedisBackend` is covered command-for-command by `fakeredis`,
  which speaks the real protocol to the real client, but it has not talked to a real
  server yet.

**Next: Phase 3 — Amazon Bedrock and the Nova client.**
`NovaClient`, `BaseAgent` and a single structured Triage Agent, with model configuration
centralised and budgets enforced from the first agent rather than added later.
