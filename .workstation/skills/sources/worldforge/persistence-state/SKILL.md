---
name: persistence-state
description: "Use for WorldForge local state: run workspaces and artifacts under `.worldforge/` (run manifests, evidence bundles, retention/prune), the `WorldForge(state_dir=...)` directory, and JSON-native artifact validation. The symbolic `World` JSON store and the `worldforge world` CLI were removed; there is no world persistence. Protects local state from silent corruption."
---

# Persistence And State

## Contract

- WorldForge has **no symbolic world store**. The mutable `World` runtime, `create_world`/
  `save_world`/`load_world`/`export_world`/`import_world`/`fork_world`, `.worldforge/worlds`, and the
  `worldforge world` CLI were removed in the latent-planning pivot. Planning is done with
  `LatentMPCController` over the `score`/`predict` capabilities; `worldforge predict` rolls a single
  move through a `predict` provider over an in-process `world_state` dict (not persisted).
- The remaining local state is **run workspaces and artifacts** under `.worldforge/` (default
  `state_dir`): run manifests, evidence/issue bundles, evaluation/benchmark reports, and run-index
  data. It is local-first and single-writer; hosts own durable storage.
- All public/semi-public artifacts are JSON-native (string keys, finite numbers, lists, objects,
  bools, strings, null). Malformed persisted/provider artifacts raise `WorldStateError`; never
  silently coerce invalid state.
- Treat existing `.worldforge/` user state as off-limits unless the user points at a disposable
  directory. Tests must use `tmp_path`.

## Workflow

1. Build provider input `world_state` as a plain dict (e.g. `{"schema_version":1,"id":...,
   "scene":{"objects":{obj.id: SceneObject(...).to_dict()}}}`); pass it to `forge.predict(...)`.
   There is no `World` object to mutate or persist.
2. Use the run-workspace surface (`worldforge runs ...`, `runs_prune`, evidence bundles) for
   anything that must survive a process: write through the validated workspace/manifest APIs in
   `src/worldforge/harness/workspace.py` and `src/worldforge/runs_prune.py`.
3. Validate serialized artifacts before filesystem writes and after reads; reject unsafe IDs,
   traversal, and non-JSON-native fields loudly.
4. Keep CLI handlers thin; do not duplicate validation or file I/O rules in `src/worldforge/cli.py`.
5. Test flows with `tmp_path` state dirs. Never use or delete the user's real `.worldforge/` state.

## Definition Of Done

- Artifact validators reject unsafe IDs, malformed payloads, and non-JSON-native fields loudly.
- CLI handlers delegate to the workspace/forge APIs rather than duplicating file I/O contracts.
- Regression tests cover both the changed happy path and the invalid persisted/provider-state path.
- Docs or command help include the command, success signal, and first recovery step when behavior
  changes.

## Do Not Add

- A symbolic world store, world persistence, or a `worldforge world` command (removed by design).
- Lock files, SQLite/database adapters, remote persistence, or multi-writer service durability —
  these need explicit design approval because persistence is host-owned beyond local run state.

## Sharp Edges

| Symptom | Cause | Fix |
| --- | --- | --- |
| `forge.predict` ignores a move | `world_state` dict has no `scene.objects` to move | Seed objects in the dict before predicting (mock mutates `state["scene"]["objects"]`) |
| Run bundle/prune rejects an entry | Manifest or artifact payload invalid | Validate the serialized payload against the workspace validators |
| Artifact leaks host paths/secrets | Unsanitized field in a public artifact | Redact via the provider/observable redaction helpers before writing |
