# AWS BetterOps Agent

An AI-powered production incident investigation and remediation platform.

AWS BetterOps Agent correlates logs, metrics, source-code changes, deployments, database
diagnostics, engineering documentation, and historical incidents to identify likely root
causes, build evidence-backed explanations, and propose validated fixes.

It is **not** a chatbot. The product is an automated engineering investigation system: an
orchestrator drives a set of specialised agents, each agent gathers evidence through
narrow Model Context Protocol (MCP) tools, and a reasoning agent correlates that evidence
into a root-cause report backed by an evidence graph.

```
        Incident ──▶ Triage ──▶ Specialist agents (parallel) ──▶ Evidence store
                                        │                              │
                                   MCP tools + RAG                     ▼
                                                              Root Cause Agent
                                                                       │
                                                        Evidence graph ─┴─ Fix Agent
                                                                            │
                                                          Sandbox validation ┴ Human approval ──▶ PR
```

---

## Status

| Phase | Scope | State |
|-------|-------|-------|
| 0 | Architecture, plan, repo scaffolding | Complete |
| 1 | Flask app, auth, projects, incidents, frontend | Complete |
| 2 | Redis cache-aside, rate limiting, structured logging | Complete |
| 3 | Bedrock / Nova client, BaseAgent, Triage Agent | Not started |
| 4–16 | MCP, RAG, orchestration, SQS, remediation, evaluation, AWS deploy | Not started |

Full breakdown: [`implementation_plan.md`](implementation_plan.md).
Design rationale: [`architecture.md`](architecture.md).

---

## Tech stack

| Concern | Choice |
|---|---|
| Web framework | Flask 3 (server-rendered Jinja + JSON API) |
| Frontend | HTML, CSS, vanilla JS (no React, no build step) |
| ORM / migrations | SQLAlchemy 2.0 + Alembic |
| Database | PostgreSQL 16+ with `pgvector` (from Phase 7) |
| Cache / rate limit | Redis (Phase 2) |
| Queue | Amazon SQS, LocalStack locally (Phase 9) |
| LLM | Amazon Nova 2 Lite via Amazon Bedrock Converse API |
| Embeddings | Amazon Titan Text Embeddings V2 via Bedrock |
| Tooling protocol | Model Context Protocol (custom servers) |
| Tests | pytest |

---

## Quick start (local)

### Prerequisites

- Python 3.11+
- PostgreSQL 16+ running locally, **or** Docker Desktop (for `docker-compose.yml`)

### 1. Install

```bash
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env          # Windows: copy .env.example .env
```

Edit `.env` and set at least `SECRET_KEY` and `DATABASE_URL`.

Generate a secret key:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

### 3. Start infrastructure

With Docker:

```bash
docker compose up -d postgres redis
```

Without Docker, use a local PostgreSQL server and create the database:

```bash
createdb betterops
```

If neither is available yet, the current schema is portable enough to run on SQLite —
set `DATABASE_URL=sqlite+pysqlite:///betterops.db` in `.env`. This is a stopgap: pgvector
(Phase 7) requires PostgreSQL.

Redis is likewise optional for local work. Set `CACHE_BACKEND=memory` to use a
per-process cache with the same TTL and invalidation semantics, or `disabled` to turn
caching off entirely. The application also degrades on its own if Redis goes away:
lookups are counted as errors and served from PostgreSQL, and rate limiting fails open.

### 4. Apply migrations

```bash
alembic upgrade head
```

### 5. Run

```bash
python app.py
```

Open <http://localhost:5000>. Register an account — the first registration creates your
organization automatically.

### 6. Tests

```bash
pytest
```

The suite runs against in-memory SQLite by default, so no infrastructure is required.
To run it against PostgreSQL instead:

```bash
# PowerShell
$env:TEST_DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/betterops_test"
pytest
```

---

## Repository layout

```
app.py                  Application factory + dev entrypoint
config.py               Environment-driven configuration (single source of truth)
constants.py            Domain vocabularies (statuses, severities, roles)
errors.py               Error hierarchy and the JSON error contract
logging_config.py       Text and JSON log formatters
routes/                 HTTP layer — thin, no business logic
services/               Business logic and orchestration of repositories
repositories/           All database access
cache/                  Cache backends, cache-aside helpers, counters
middleware/             Auth, request logging, rate limiting
schemas/                Pydantic request/response validation
database/               Engine, session, models
migrations/             Alembic migration scripts
templates/              Jinja templates
static/css, static/js   Frontend assets
tests/                  pytest suite
```

Directories for later phases (`agents/`, `orchestration/`, `llm/`, `mcp_clients/`,
`mcp_servers/`, `rag/`, `workers/`, `simulator/`) are created as their phase begins —
see `implementation_plan.md`. Empty placeholder packages are intentionally not committed.

---

## Design rules enforced in this codebase

1. Route handlers contain no business logic — they parse, delegate, and serialise.
2. Services never execute SQL; repositories never make policy decisions.
3. Every tenant-scoped query filters on `organization_id`, and every tenant-scoped cache
   key contains it.
4. No credentials, model IDs, TTLs, or endpoints are hard-coded — everything comes from
   `config.py`.
5. A cache failure is never a request failure. Redis is a performance layer, never a
   source of truth.
6. AI-generated code never touches production. Remediation is sandboxed and human-approved.
7. Agents receive only the tools their role requires.
8. Structured logs never contain secrets — the formatter emits an explicit field list and
   redacts known-sensitive names.

---

## Security notes

- Passwords are hashed with scrypt (`werkzeug.security`).
- Sessions use a signed JWT stored in an `HttpOnly`, `SameSite=Strict` cookie; `Secure`
  is enabled automatically outside development. Tokens are never placed in `localStorage`.
- All customer database access (Phase 6) is read-only and statement-timeout bounded.
- Customer credentials live in AWS Secrets Manager; the application database stores only
  references.
