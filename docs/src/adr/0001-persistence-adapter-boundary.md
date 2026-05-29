# ADR 0001: Persistence Adapter Boundary

Status: Accepted

Date: 2026-04-30

## Context

WorldForge persists worlds today as validated local JSON files. That store is intentionally
single-writer and is useful for tests, examples, local harness workflows, and checkout-safe issue
evidence. Host applications that run services, batch workers, or robot labs can need multi-writer
durability, locking, backup/restore, retention policy, and schema migrations.

Adding a database directly to core would blur the line between WorldForge's framework contract and
host-owned deployment responsibilities. A durable store also needs operational decisions that
WorldForge cannot infer from a library call: transaction isolation, lease ownership, backup cadence,
retention windows, migration rollout, and incident recovery.

## Decision

WorldForge keeps local JSON as the default persistence behavior. Durable multi-writer persistence
must enter through an explicit `WorldPersistenceAdapter` boundary before any implementation is
accepted into core, an optional extra, or a reference host.

The adapter boundary is:

```text
WorldPersistenceAdapter
  save(world) -> None
  load(world_id) -> World
  list() -> list[WorldSummary]
  delete(world_id) -> None
  export(world_id) -> dict
  import(payload, *, new_id: str | None = None) -> World
  health() -> PersistenceHealth
```

Every implementation must preserve the current local JSON invariants:

- validate world IDs before addressing storage;
- validate serialized world payloads before writes and after reads;
- fail loudly on malformed state, missing worlds, failed writes, and unsafe identifiers;
- keep provider secrets, signed URLs, host paths, and private payloads out of exported issue
  evidence;
- emit enough typed error context for operators without requiring database-specific exceptions.

The first durable implementation, if accepted later, should be an optional adapter or reference
host integration. It must not add a database dependency to the base package.

## Required Adapter Design

A future implementation PR must include:

- **Locking:** define single-writer, optimistic concurrency, advisory locks, lease ownership, and
  stale-lock recovery.
- **Migrations:** define schema version storage, forward migration ordering, rollback policy, and
  how old WorldForge clients fail.
- **Backup and restore:** document which payloads are sufficient to restore worlds, how integrity is
  checked, and what the recovery drill looks like.
- **Retention:** separate world state retention from run-workspace evidence retention and document
  deletion guarantees.
- **Schema versioning:** store an adapter schema version separately from the WorldForge package
  version and validate it before reads or writes.
- **Failure recovery:** specify retryable versus terminal failures, partial-write cleanup, and
  operator-facing diagnostics.

## Rejected Alternatives

### Replace Local JSON With SQLite

SQLite is attractive for local workflows, but replacing JSON would change the default persistence
surface, add migration complexity to simple examples, and still not solve distributed multi-writer
coordination for service hosts.

### Add Lock Files Around The Current Store

Lock files would make local JSON look safer than it is. They do not define backup, migration,
retention, or cross-host recovery, and their behavior varies by filesystem.

### Add A Generic Database URL Setting

A connection string alone does not define the storage contract. Without an adapter design,
WorldForge would be responsible for unknown locking, transaction, migration, backup, and recovery
semantics.

### Move Persistence Entirely Out Of WorldForge

WorldForge still needs local JSON for deterministic tests, examples, harness workflows, and issue
reproduction. Removing it would make the checkout experience worse and push basic state validation
into every host.

## Consequences

- Current local JSON behavior remains authoritative and unchanged.
- Host applications remain responsible for production databases, backups, retention, and
  multi-writer coordination.
- WorldForge can still document a future durable adapter without adding a base dependency.
- Any future persistence adapter has a named boundary and acceptance bar before implementation.

## Validation

The default persistence contract remains covered by existing local JSON and CLI tests:

```bash
uv run pytest tests/test_persistence*.py tests/test_cli_worlds.py
```

The ADR and linked documentation are validated by:

```bash
uv run pytest tests/test_docs_site.py
uv run mkdocs build --strict
```
