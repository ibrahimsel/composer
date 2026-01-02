# Backend Responsibilities Technical Analysis (Open Source)

This document summarizes the backend responsibilities implied by the dashboard
UI and docs. It assumes the frontend will move from mock data to a real API.

## Scope and Inputs

Primary sources:
- `docs/vehicle_status.md` (statuses + reason codes)
- `docs/vehicle_events.md` (timeline events)
- `docs/rollouts.md` (rollout stages, gates)
- `docs/audit_log.md` (audited actions)
- `src/ARCHITECTURE.md` (API contract + data flow)

## Core Responsibilities

### 1) Authoritative Data Model and Storage
The backend owns the source of truth for:
- Vehicles (desired vs actual state, status, reason codes, metadata)
- Desired states (requested configuration per vehicle or target set)
- Releases (stack versions, signatures, metadata)
- Rollouts (status, canary + wave stages, gates, metrics)
- Timeline events (for vehicle history)
- Audit log entries (who did what, when, and why)
- Reports (health, reconcile outcomes)

Derived aggregates should be materialized or computed efficiently for the UI:
fleet counts by status, top reason codes, rollout progress, and per-vehicle
status summaries.

### 2) API Contract and Query Behavior
Expose the production API surface defined in `src/ARCHITECTURE.md`, including:
- Read endpoints for vehicles, rollouts, releases, desired states, and reports.
- Write endpoints for creating desired states and managing rollouts.

API responsibilities:
- Server-side pagination, filtering, search, and sorting.
- Stable response envelope (`data`, `metadata`, `timestamp`).
- Consistent error codes/messages for invalid inputs or policy violations.

### 2a) API Versioning and Compatibility Plan
- Base path versioning (for example, `/api/v1`).
- OpenAPI spec as the source of truth (`docs/openapi.yaml`), versioned with SemVer.
- Backward-compatible additions in minor versions; breaking changes require `/api/v2`.
- Deprecation policy with `Deprecation` and `Sunset` headers plus documented timelines.
- Idempotency keys for write requests to support safe retries.

### 3) Rollout Orchestration and Reconciliation
The backend must execute declarative rollouts:
- Expand targets into concrete vehicle sets.
- Create desired states, schedule canary + wave progression.
- Evaluate gates (`canaryHealthy`, `failureThreshold`, `safetyChecks`).
- Support pause and rollback actions with safe, idempotent behavior.
- Use a queue + worker/reconciler to apply state changes reliably.

### 4) Vehicle Telemetry Ingestion
The backend must ingest and normalize device updates:
- Heartbeats (for offline detection and health signals).
- Timeline events (`desired_notified`, `apply_start`, `ready`, `failed`, `blocked`).
- Reason codes (e.g., `BATTERY_LOW`, `NETWORK_UNREACHABLE`).

Responsibilities include deduplication, ordering, and persistence of timeline
events, plus computing the current status for each vehicle.

### 5) Safety Policy Enforcement
Safety policy is not a UI concern only; it must be enforced server-side:
- Enforce stationary requirements, battery thresholds, time windows.
- Block progression when safety checks fail.
- Prevent weakened safety policies without explicit, audited intent.

### 6) Audit and Compliance
The backend is responsible for:
- Emitting audit log entries for every write action.
- Capturing actor identity, correlation IDs, timestamps, and payloads.
- Retention policies and exportability for incident review.

### 7) Authentication, Authorization, and Scoping
Minimum roles are Viewer and Operator:
- Viewer: read-only access.
- Operator: write access (create deployments, pause, rollback).

Backend responsibilities include token validation, RBAC enforcement, and
scoping across regions, models, or organizational boundaries.

### 8) Real-Time Updates and Client Sync
The UI expects near-real-time updates:
- WebSocket or SSE for vehicle status, rollout progress, and audit events.
- Delta updates to avoid full reloads.
- Backfill and resync behavior on reconnect.

### 9) Observability and Operational Tooling
Operational requirements for production and open source:
- Structured logs with redaction of sensitive data.
- Metrics for rollout success rates, failures, and latency.
- Tracing for request-to-reconcile paths.
- Health and readiness probes.

### 10) Data Integrity and Reliability
Guarantees needed by the dashboard:
- Idempotent write APIs.
- Consistency checks between desired and actual state.
- Clear handling of out-of-order or missing device events.

### 11) Performance and Scale
Expected scale implies:
- Indexed queries for filters (model, region, ring, status).
- Server-side pagination and caching.
- Batch processing and backpressure for telemetry spikes.

## Open-Source-Specific Responsibilities

### Configuration and Secrets
- Environment-variable driven config with documented defaults.
- No hard-coded secrets; clear guidance for secret storage.

### Pluggable Integrations
- Identity provider integration points (OIDC/JWT).
- Artifact registry integration for release metadata and signatures.
- Message queue/storage abstractions to avoid vendor lock-in.

### Documentation and API Stability
- Versioned API contract and changelog.
- OpenAPI/Swagger docs and examples, with `docs/openapi.yaml` as the canonical stub.
- Migration guides for schema changes.

### Security and Privacy
- Secure-by-default settings (rate limits, auth required for writes).
- Optional audit-log redaction and encryption at rest guidance.
- Vulnerability reporting policy and dependency hygiene.

### Developer Experience
- Local dev setup with sample data and seed scripts.
- Test suite for core workflows (create rollout, pause, rollback).
- Docker-compose or similar for reproducible runs.

## Suggested Service Boundaries (Logical)
- API service (REST + WebSocket/SSE).
- Ingestion service (telemetry + timeline events).
- Rollout orchestrator + reconciler workers.
- Datastore + queue + cache.

These can be combined for a small deployment and separated for scale.

## Non-Goals (Aligned with the UI)
- No direct remote command execution (declarative desired state only).
- No log scraping as a primary debugging interface.
