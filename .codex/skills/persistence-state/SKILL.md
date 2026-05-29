---
name: persistence-state
description: "Use for WorldForge local JSON persistence, world CLI commands, world IDs, history entries, import/export/fork behavior, state validation, scene-object mutations, and recovery of `.worldforge/worlds` data. Protects persisted state from silent corruption."
---

# Persistence And State

## Contract

- Persistence is local JSON under `.worldforge/worlds` by default.
- It is single-writer only; hosts own durable storage beyond import/export.
- World IDs are file stems. Reject path separators, traversal, and unsafe values before load, import, or save.
- Malformed persisted/provider state raises `WorldStateError`.
- Do not silently coerce invalid state.

## Workflow

1. Reuse `WorldForge.create_world`, `create_world_from_prompt`, `save_world`, `load_world`, `export_world`, `import_world`, and `fork_world`.
2. Keep CLI handlers thin; do not duplicate persistence validation or file I/O rules in `src/worldforge/cli.py`.
3. Validate serialized state before filesystem writes and after filesystem reads.
4. Preserve history contract: non-negative steps, non-empty summaries, valid snapshot states, valid serialized `Action` payloads when present, and no entry step greater than current world step.
5. Scene object add/update/remove mutations append typed history entries without advancing provider time.
6. Position patches translate bounding boxes by the same delta as object poses.
7. Test CLI flows with `tmp_path` state dirs. Never use or delete the user's real `.worldforge/` state.

## Do Not Add

- Lock files.
- SQLite or database adapters.
- Remote persistence.
- Multi-writer service durability.

Those need explicit design approval because persistence is currently host-owned beyond local JSON.

## Sharp Edges

| Symptom | Cause | Fix |
| --- | --- | --- |
| Load rejects world ID | Unsafe file-stem shape | Use CLI-generated ID or sanitize before save/import |
| Fork/import fails | Snapshot history or action payload invalid | Validate serialized payload against framework validators |
| Object bbox drifts after move | Pose patch did not translate bounds | Update bbox by same delta as position |
