# AWS BetterOps Agent — Architecture

This document records the system design and, more importantly, the reasoning behind each
decision. It is the reference that later phases must stay aligned with.

---

## 1. What the system does

When a production service degrades, the evidence needed to explain it is spread across
CloudWatch, GitHub, deployment history, the application database, runbooks, and previous
postmortems. An engineer normally correlates these by hand.

AWS BetterOps Agent performs that correlation automatically:

1. An incident arrives (created manually, or later via alert webhook).
2. An investigation is queued and processed asynchronously by a worker.
3. A **Triage Agent** decides which evidence domains matter.
4. **Specialist agents** run concurrently, each restricted to one domain and one MCP
   server, and each returning *structured evidence* — never conclusions.
5. A **Root Cause Agent** receives only the structured evidence and produces a report
   that must cite existing evidence IDs.
6. Evidence and its causal relationships are persisted as an **evidence graph**.
7. A **Fix Agent** optionally proposes a patch, which is validated in an isolated
   sandbox and only reaches GitHub after explicit human approval.

The separation in step 4/5 is the core design idea: **evidence gathering and reasoning
are different jobs performed by different agents with different inputs.** That separation
is what makes hallucination detectable — the reasoning agent can only cite records that
already exist in the database.

---

## 2. Architectural principles

| # | Principle | Consequence in the code |
|---|-----------|-------------------------|
| 1 | The LLM is a component, not the architecture | Flask → service → queue → worker → orchestrator → agents. No route calls a model directly. |
| 2 | Evidence before assertion | Specialist agents emit `Evidence` rows. The Root Cause Agent's output is schema-validated against those rows. |
| 3 | Least privilege everywhere | Narrow MCP tools (`get_slow_queries`, not `execute_sql`); per-agent tool allowlists; read-only DB roles; scoped IAM. |
| 4 | Bounded work | Every agent has max tool calls, max model calls, and a wall-clock deadline. Every investigation has a token budget. |
| 5 | Degrade, don't fail | If GitHub is unreachable the investigation continues and records `unavailable_sources`; confidence is reduced accordingly. |
| 6 | Humans approve side effects | Nothing writes to a customer system without an explicit approval action. |
| 7 | Multi-tenancy is a data invariant | Every tenant-scoped table carries `organization_id`; every repository query filters on it. |

---

## 3. Runtime topology

```
                                  Internet
                                     │
                              Application Load Balancer
                                     │
                          ┌──────────┴──────────┐
                          ▼                     ▼
                  ECS Fargate: web        ECS Fargate: worker
                  (Flask, gunicorn)       (SQS consumer)
                          │                     │
          ┌───────────────┼──────────┐          │
          ▼               ▼          ▼          ▼
   RDS PostgreSQL   ElastiCache   S3        Agent Orchestrator
   (+ pgvector)       Redis      docs             │
          ▲               ▲                       │
          │               │        ┌──────────────┼──────────────┐
          └───────────────┴────────┤              ▼              ▼
                          SQS ─────┘        Bedrock          MCP servers
                                          (Nova 2 Lite,   ┌─────┼─────┬──────────┐
                                           Titan V2)   GitHub  AWS  Postgres  Knowledge
                                                          │     │      │         │
                                                       GitHub  CW   customer   pgvector
                                                        API    API     DB        RAG
```

The web tier and worker tier are separate ECS services running the same image with
different entrypoints. They scale independently: web scales on request concurrency,
workers scale on SQS queue depth.

---

## 4. Backend layering

```
HTTP request
   → middleware        (request id, auth, rate limit, logging)
   → route             (parse + validate input, serialise output)
   → service           (business rules, transactions, cache policy, authorisation)
   → repository        (SQL only)  |  agent / MCP client / external API
   → service
   → route
HTTP response
```

Rules that are actually enforced by review:

- **Routes** may call services and `schemas`. They may not import `database` or build
  queries. A route is typically 5–15 lines.
- **Services** own business rules, transaction boundaries, cache-aside logic, and
  authorisation checks. They receive a `Session` and pass it to repositories rather than
  opening their own — this keeps a request in one transaction.
- **Repositories** are the only place SQLAlchemy queries are written. They take explicit
  scoping arguments (`organization_id`) and return models or `None`. They never raise
  HTTP-shaped errors.
- **Errors**: services raise `ApiError` subclasses (`NotFoundError`, `ConflictError`,
  `ValidationError`, `AuthError`, `ForbiddenError`). A single error handler converts them
  to the JSON error contract. Route handlers contain no try/except for control flow.

### Error contract

Every failure returns the same shape, so the frontend has one code path:

```json
{ "error": { "code": "not_found", "message": "Incident not found", "details": {} } }
```

---

## 5. Data model

Two databases are involved and must never be confused:

| | AWS BetterOps Agent database | Customer database |
|---|---|---|
| Contains | users, organizations, projects, incidents, investigations, agent runs, tool calls, evidence, documents, vectors | orders, customers, payments — the customer's own data |
| Owned by | this platform | the customer |
| Access | read/write via SQLAlchemy | **read-only**, through the PostgreSQL MCP, with statement timeouts and row limits |

### Phase 1 tables

```
users ──< organization_members >── organizations
                                        │
                                        ├──< projects ──< incidents
                                        │
                                        └── (later) integrations, documents, …
```

| Table | Purpose | Key columns / indexes |
|---|---|---|
| `users` | Identity and credentials | `email` unique (lowercased), `password_hash` |
| `organizations` | Tenant boundary | `slug` unique |
| `organization_members` | Membership + role | unique `(organization_id, user_id)`; role `owner`/`admin`/`member` |
| `projects` | A deployed system under observation | unique `(organization_id, key)` |
| `incidents` | A production problem | index `(project_id, created_at desc)`, `(organization_id, status)`; `reference` unique per org |

Design notes:

- Status/severity/role values are stored as `VARCHAR` with constants and a check-style
  validation in the service layer, not as PostgreSQL `ENUM` types. Changing an `ENUM` is
  a migration with a lock; adding a status will be routine in this project (investigation
  statuses especially). Constants also keep the schema portable so the test suite can run
  on SQLite without infrastructure.
- Timestamps are `TIMESTAMP WITH TIME ZONE`, always UTC. The database supplies
  `created_at`/`updated_at` defaults so out-of-band writers (workers) stay consistent.
- Incidents carry both `started_at` (when the problem began in production — the value
  agents correlate against) and `created_at` (when the record was written). These are
  different and both matter for timeline correlation.

### Tables added in later phases

`integrations`, `repositories`, `investigations`, `agent_runs`, `tool_calls`,
`evidence_nodes`, `evidence_edges`, `root_cause_reports`, `documents`,
`document_chunks`, `remediation_plans`, `remediation_runs`, `evaluation_scenarios`,
`evaluation_runs`. Each is created in the migration for the phase that needs it.

### Multi-tenancy

Every tenant-scoped repository method takes `organization_id` as a required parameter and
includes it in the `WHERE` clause. Fetch-then-check is not used, because a missing check
leaks existence. A user's organization is resolved once per request from the session
token and attached to the request context.

---

## 6. Authentication

- Passwords are hashed with **scrypt** via `werkzeug.security` (bundled with Flask; no
  additional dependency, memory-hard, sensible defaults).
- The session is a **JWT** signed with `SECRET_KEY` (HS256), carrying `sub` (user id),
  `org` (organization id), `iat`, `exp`, `jti`.
- The token is delivered in a cookie that is `HttpOnly`, `SameSite=Strict`, `Path=/`, and
  `Secure` whenever the app is not in development. It is never written to `localStorage`,
  so XSS cannot exfiltrate it.
- `SameSite=Strict` is the CSRF defence for Phase 1: a cross-site request cannot attach
  the cookie. When the API later needs cross-origin clients, a double-submit CSRF token
  is added rather than relaxing the cookie.
- **Why JWT over server-side sessions:** the worker tier and multiple web tasks are
  horizontally scaled and stateless; a shared session store would be another dependency
  in the request path. The cost is that logout cannot invalidate an outstanding token —
  accepted for now with a short lifetime (default 12 h), and a `jti` denylist in Redis is
  the documented upgrade in Phase 2.

---

## 7. Agents

Every agent is a distinct component with its own system prompt, tool allowlist, output
schema, and execution limits. They are not one prompt with different text.

| Agent | Input | Output | Tools |
|---|---|---|---|
| Triage | incident, service, timestamps, alert metadata | required agents, initial hypotheses | none |
| Observability | incident window, service | evidence[] | AWS Observability MCP |
| Deployment | incident window, service | evidence[] | Deployment MCP |
| Code | suspect commits/services | evidence[] | GitHub MCP |
| Database | incident window | evidence[] | PostgreSQL MCP (read-only) |
| Knowledge | incident text, symptoms | evidence[] | Knowledge MCP (RAG) |
| Root Cause | all evidence, timeline, unavailable sources | root cause, confidence, cited evidence IDs, alternatives | none |
| Fix | root cause + code evidence | patch, rationale, validation plan | GitHub MCP (read) |

Prompts require agents to label statements as `OBSERVATION`, `INFERENCE`, `HYPOTHESIS`,
or `CONCLUSION`, and to report uncertainty instead of inventing information.

`BaseAgent` owns the loop that is identical across agents: build messages, call
`NovaClient`, dispatch tool calls to allowed MCP clients, record every call in
`tool_calls`, enforce budgets, parse and validate the structured output, retry once on
schema failure with the validation error fed back.

### Model access

All generation goes through a single `NovaClient` wrapping the Bedrock **Converse** API.
Agents never construct a boto3 client. Model id, region, temperature, max tokens, and
step limits come from `config.py`. This is what makes "swap the model per agent later" a
configuration change rather than a rewrite.

We deliberately do **not** use Bedrock Agents for orchestration — building the
orchestrator is a primary goal of the project, and it is also what gives us tool-call
auditing, budgets, partial-failure handling, and evaluation hooks.

---

## 8. Orchestration

```
investigation queued
   → TRIAGING           Triage Agent selects specialists
   → COLLECTING_EVIDENCE specialists run concurrently (thread pool, per-agent deadline)
   → ANALYZING          Root Cause Agent consumes aggregated evidence
   → COMPLETED | FAILED | CANCELLED
```

The orchestrator, not the agents, owns: execution order, concurrency, per-agent and
global budgets, timeouts, retries, evidence aggregation, partial-failure handling, and
state transitions. Agents never call each other. `InvestigationState` is the single
mutable object passed through the pipeline and persisted at each transition, which is
what makes the frontend's polling endpoint meaningful.

Specialist agents are independent, so they run in parallel. Because each agent's work is
I/O-bound (Bedrock + MCP calls), a thread pool is sufficient and avoids making the whole
codebase async.

---

## 9. MCP layer

MCP is the standard interface between agents and external systems. It does not replace
APIs — MCP tools call APIs underneath:

```
Code Agent → MCP client → GitHub MCP server → GitHub REST API
```

Five servers: GitHub, AWS Observability, PostgreSQL diagnostics, Deployment, Knowledge.

Each tool is narrow by design. `search_logs` and `get_slow_queries` are acceptable;
`execute_arbitrary_sql`, `run_shell_command`, and `execute_any_aws_command` are not — a
broad tool means the agent's prompt is the only thing standing between a model and a
destructive action.

The PostgreSQL server additionally: connects with a read-only role, rejects any statement
that is not `SELECT`/`EXPLAIN` before it reaches the driver, sets `statement_timeout`,
wraps queries in a read-only transaction, and caps returned rows.

Every tool invocation is recorded in `tool_calls` (agent, tool, arguments, timings,
status, result summary, error) with secrets redacted. This audit trail is both a
debugging tool and the data source for evaluation metrics.

---

## 10. RAG

Built in-house rather than delegated to a hosted Knowledge Base, because the pipeline is
part of what this project demonstrates.

```
upload → S3 → extract text → chunk → Titan Text Embeddings V2 → pgvector → retrieve
```

- Chunking is structure-aware for Markdown (split on headings, then size-bounded with
  overlap) so a runbook section stays intact.
- Every chunk stores `organization_id`, `project_id`, `document_type`, `service`,
  `source`, and `section`. Retrieval filters on organization and project **in SQL**, not
  after ranking — cross-tenant retrieval must be impossible, not merely unlikely.
- Retrieval combines vector similarity with metadata filters, and returns the source
  document and section so the Knowledge Agent's evidence is citable.

Generation stays on Nova 2 Lite; only embeddings use Titan V2.

---

## 11. Caching

Redis, cache-aside. Read: check cache → on miss, read source → write cache with TTL →
return. Write: update the source of truth, then delete the affected keys.

Keys are `betterops:{version}:{namespace}:{parts…}`. The version prefix lets an
incompatible change to a cached shape invalidate everything at once; the namespace lets a
family of keys be dropped with one pattern delete (via `SCAN`, never `KEYS`).

| Key | TTL |
|---|---|
| `…:incident:{org}:{id}` | 5 min |
| `…:github_commits:{repo}` | 60 s |
| `…:github_file:{repo}:{sha}:{path}` | 5 min |
| `…:cloudwatch:{…}` | 10 s |
| `…:integration:{id}` | 5 min |
| `…:rag:{project}:{query_hash}` | 15 min |

All TTLs are configurable in `config.py`. Secrets, credentials and tokens are never
cached. Mutating an incident deletes its key — **after** the commit, never before, or a
concurrent reader would repopulate the cache with the pre-update row.

Three invariants hold throughout `cache/`:

1. **A cache failure is never a request failure.** Backend errors are translated to
   `CacheUnavailable`, counted, and treated as a miss. A Redis outage makes the
   application slower, not broken.
2. **Every value has a TTL.** Even a missed invalidation ages out.
3. **Tenancy is in the key, not just in the query behind it.** `incident:{org}:{id}`
   cannot be served to the wrong organization even if ids were guessed.

`None` is never cached, because it is indistinguishable from a miss. Loader exceptions
propagate uncached, so a 404 is never stored as though the record existed.

### Backends

One narrow interface (`get`, `set`, `delete`, `delete_matching`, `increment`, `ping`) with
three implementations: `RedisBackend` (real), `MemoryBackend` (per-process dict with the
same TTL semantics, for tests and for local development without Redis) and `NullBackend`
(caching off). The interface is small on purpose — it is the complete list of Redis
features this system depends on.

### Rate limiting

Fixed window per identity per route class, counted in Redis so the limit holds across ECS
tasks. The window start is part of the key, so counters reset by expiring. Authenticated
requests are limited per user (the unit that consumes agent work and Bedrock tokens);
auth endpoints are limited per client address, because there is no user yet and the point
is to slow credential guessing. Exceeding a limit returns `429` with `Retry-After`.

The limiter **fails open** when Redis is unreachable. Rate limiting protects cost and
fairness; refusing every request during a cache outage would turn a degraded dependency
into an outage of our own. A fixed window permits up to 2× the limit across a boundary,
which is acceptable here — the investigation endpoint gets a distributed lock in Phase 9,
and that is the control that actually matters for expensive work.

Redis is **not** the investigation queue. Durability and redelivery matter for
multi-minute AI jobs, so the queue is SQS.

---

## 12. Asynchronous processing

`POST /api/incidents/{id}/investigate` creates an investigation row, enqueues a job, and
returns `202 Accepted` with `{investigation_id, status: "queued"}`. It never blocks.

The worker consumes SQS, runs the orchestrator, and updates investigation state. Job
handling is idempotent: an investigation already in a terminal or active state is not
restarted, and a Redis lock keyed on the incident prevents duplicate launches from
concurrent requests. Visibility timeout exceeds the maximum investigation duration; a
dead-letter queue captures repeated failures.

The frontend polls `GET /api/investigations/{id}` every few seconds. Server-Sent Events
are an optional later refinement, not a prerequisite.

---

## 13. Remediation

```
root cause → Fix Agent → patch → sandbox (Docker locally, CodeBuild/isolated ECS in AWS)
           → unit + integration tests, lint, static analysis, benchmark
           → before/after metrics → human review → optional pull request
```

The sandbox has no production credentials, no production AWS write permissions, and no
production secrets; it uses fixtures and an isolated database. A pull request is created
only on explicit approval, on a new branch, and is never merged automatically.

---

## 14. Evaluation

A simulator application contains deliberately introduced failures with known ground
truth (`DATABASE_N_PLUS_ONE`, `DATABASE_MISSING_INDEX`,
`DATABASE_CONNECTION_EXHAUSTION`, `APPLICATION_EXCEPTION`, `CONFIGURATION_ERROR`,
`EXTERNAL_API_TIMEOUT`, `FAILED_DEPLOYMENT`, `CPU_EXHAUSTION`).

Primary scoring is **deterministic**: the agent's predicted root-cause category is
compared to the ground-truth category. An LLM judge may add a qualitative score, but it
is never the primary metric — grading a model with a model hides correlated failure.

Tracked: top-1 and top-3 accuracy, investigation latency, tool calls, LLM calls, tokens,
estimated cost, cache hit rate, and unsupported-claim rate. Configurations
(single agent / multi-agent / +RAG / +MCP) are comparable because the metrics come from
the `agent_runs` and `tool_calls` audit tables rather than from ad-hoc instrumentation.

---

## 15. Failure handling

Every external integration has a timeout, bounded retries with backoff, and a circuit
breaker. A failing source degrades the investigation instead of ending it: the
orchestrator records `unavailable_sources`, passes it to the Root Cause Agent, and the
resulting confidence reflects the missing evidence. A report that says "94% confident,
GitHub unavailable" would be a bug.

---

## 16. Observability of the platform itself

Structured JSON logs carry `request_id`, `user_id`, `organization_id`,
`investigation_id`, `agent`, `tool`, `duration_ms`, and `status` as first-class fields
rather than as substrings to grep. `text` format is the default in development only.

Passwords, tokens, credentials and secrets are never logged: the formatter emits only the
record's explicit `extra` fields, redacts any field whose name matches a known-sensitive
list, and request logging records the path without the query string. Request bodies,
headers and cookies are never serialised.

Cache hit/miss/error counters are recorded from Phase 2 and exposed at
`GET /api/system/cache`, because hit rate is one of the metrics the Phase 15 evaluation
platform reports and retrofitting it later would mean retrofitting the instrumentation
too.

`/healthz` reports the database and the cache separately. A cache outage is reported but
does **not** mark the task unhealthy — pulling every task out of the load balancer
because ElastiCache is unreachable would convert a slowdown into an outage.

Logs and metrics ship to CloudWatch, which means the platform is eventually capable of
investigating its own demo deployment.

---

## 17. Decision log

| Decision | Alternative | Why |
|---|---|---|
| Own orchestrator | Bedrock Agents | Orchestration, budgets, auditing and evaluation are the point of the project |
| Separate evidence agents from reasoning agent | one agent with all tools | Makes citations verifiable and hallucination detectable |
| SQS for investigations | Redis list / Celery | Durability, redelivery, DLQ, visibility timeout for multi-minute jobs |
| Redis for cache + rate limit + locks only | Redis for everything | Cache loss is survivable; job loss is not |
| PostgreSQL + pgvector | dedicated vector DB | One database, transactional consistency between metadata and vectors, tenant filters in SQL |
| Plain SQLAlchemy + Alembic | Flask-SQLAlchemy | Workers run outside the Flask app context; avoiding the extension keeps one data layer for both tiers |
| VARCHAR + constants | PostgreSQL ENUM | Status vocabularies will grow; avoids lock-taking migrations and keeps tests infra-free |
| JWT in HttpOnly cookie | server-side sessions | Stateless across web/worker tasks; XSS cannot read the token |
| Pydantic for validation | hand-written checks | Same library validates API input and agent structured output |
| Vanilla JS | React | Explicit requirement; also keeps the deployable a single container with no build step |
| Cache backend interface with 6 methods | use `redis.Redis` directly | Makes the Redis surface we depend on explicit, and lets the suite test cache semantics without infrastructure |
| Cache the serialised payload | cache the ORM object | A detached model would need re-attaching; a dict keeps the cached shape identical to the API contract |
| Rate limiter fails open | fail closed | A cache outage should not become an API outage; cost control is not a safety control |
| Fixed window | sliding window / token bucket | 2× burst at a boundary is acceptable at these limits; Phase 9 adds a lock where precision matters |
| Log formatter emits only `extra` fields | log request/response bodies | Bodies carry passwords and tokens; an allowlist cannot leak what it never reads |
