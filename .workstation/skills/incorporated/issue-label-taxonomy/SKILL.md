---
name: issue-label-taxonomy
description: "Trigger: creating, triaging, or labeling issues. Teaches the label system as triage language."
tags: ["workflow", "issues", "labels", "triage", "low"]
---

# Issue Label Taxonomy

## Roadmap Streams

- `stream: provider-evidence` — provider selection, adapters, promotion
- `stream: evidence-integrity` — eval suites, benchmarks, reports
- `stream: ops-authoring` — operator workflows, harness, runbooks

## Capability Labels

`predict`, `generate`, `reason`, `embed`, `transfer`, `score`, `policy`

## Domain Labels

`provider`, `research`, `artifacts`, `evaluation`, `benchmark`, `harness`, `operations`, `observability`, `persistence`, `security`, `examples`, `developer-experience`, `robotics`, `optional-dependency`

## Severity Labels

- `severity: blocking` — blocks release or public contract
- `severity: quality` — degrades quality but doesn't block
- `type: hardening` — reliability, validation, redaction

## Triage Rules

| Stream | Evidence Required |
|--------|-------------------|
| provider-evidence | Provider template, fixtures, docs, smoke evidence |
| evidence-integrity | Preserved run evidence or release evidence |
| ops-authoring | Command, success signal, triage step, recovery |

## Pattern for Any Repo

1. Define stream labels for roadmap visibility
2. Define domain labels for capability tracking
3. Define severity labels for priority
4. Document triage rules per stream

## Sharp Edges

| Symptom | Cause | Fix |
|---------|-------|-----|
| Issue lacks context | Missing labels | Add stream + domain labels |
| Triage unclear | Missing triage rules | Document evidence requirements |
