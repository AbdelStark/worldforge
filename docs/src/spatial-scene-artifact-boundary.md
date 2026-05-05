# Spatial Scene Artifact Boundary

Decision date: 2026-05-05.

Issue: [#138](https://github.com/AbdelStark/worldforge/issues/138).

Status: design accepted; provider implementation deferred.

This record defines the minimum WorldForge scene artifact boundary before any spatial or 3D scene
provider is added. It does not add a provider, viewer, renderer, simulator bridge, asset store, or
new capability.

## Decision

WorldForge will treat spatial and 3D world generation as a future `generate` surface only after
the scene artifact contract has fixture coverage and validation. The first implementation candidate
class is an OpenLRM-style local 3D reconstruction or generation runtime that emits host-owned scene
assets. This is a candidate class for artifact validation, not a public provider commitment.

No provider catalog row changes in this phase. A future provider may expose `generate` when it can
return a validated scene artifact and preserve sanitized evidence without pulling GPU runtimes,
viewers, checkpoints, or asset dependencies into the base package.

## Candidate Decision

| Candidate | Decision | Reason |
| --- | --- | --- |
| OpenLRM-style local 3D reconstruction or generation runtime | Accepted as the first artifact-contract candidate class | Public research runtimes are a reasonable source of scene outputs, but WorldForge should validate the artifact shape before selecting one adapter. |
| World Labs Marble-style hosted spatial world products | Rejected for this implementation path | Product output may be relevant to the taxonomy, but there is no WorldForge-ready callable automation contract in the current repo evidence. |
| Simulator bridges | Rejected for this provider boundary | A simulator is a host process with controller, asset, and safety ownership, not a media-generation provider by itself. |
| Cosmos, Runway, and other video APIs | Rejected for this artifact boundary | Generated videos are media artifacts, not persistent scenes with inspectable geometry, transforms, and asset references. |
| Genie-style interactive world generation | Deferred to the Genie contract decision | Genie remains a separate fail-closed scaffold until a concrete runtime or API contract exists. |

## Scene Artifact Shape

The checkout-safe artifact is a JSON object with these top-level fields:

| Field | Required | Contract |
| --- | --- | --- |
| `schema_version` | yes | String version. The first fixture schema is `1`. |
| `kind` | yes | Literal `worldforge.scene_artifact`. |
| `provider` | yes | Provider name that produced the artifact. Fixtures may use `fixture`. |
| `capability` | yes | Literal `generate` for generated scene artifacts. |
| `units` | yes | World-distance unit. Initial valid values: `meter`, `centimeter`, `millimeter`, `unitless`. |
| `coordinate_frame` | yes | JSON object defining `up_axis`, `forward_axis`, and `handedness`. |
| `objects` | yes | List of scene objects with stable IDs, transforms, optional bounds, and asset references. |
| `assets` | yes | List of referenced external or local assets, each with safe identity and digest metadata. |
| `media` | no | Optional previews, thumbnails, or camera-path renders. These are evidence aids only. |
| `provenance` | yes | Runtime, command, input digest, result digest, event count, and limitations. |
| `metadata` | no | Small JSON-native metadata only. It must not carry secrets or host-local paths. |

The artifact is intentionally descriptive. It does not prove physical validity, collision
correctness, rendering quality, grasp feasibility, or simulator compatibility.

## Coordinate And Transform Contract

`coordinate_frame` contains:

```json
{
  "up_axis": "z",
  "forward_axis": "x",
  "handedness": "right"
}
```

Valid axes are `x`, `y`, and `z`. `up_axis` and `forward_axis` must differ. Valid handedness values
are `left` and `right`.

Each scene object contains:

```json
{
  "id": "block-1",
  "label": "block",
  "transform": {
    "translation": [0.0, 0.0, 0.0],
    "rotation_quat": [0.0, 0.0, 0.0, 1.0],
    "scale": [1.0, 1.0, 1.0]
  },
  "bbox": {
    "min": [-0.05, -0.05, 0.0],
    "max": [0.05, 0.05, 0.1]
  },
  "asset_refs": ["mesh-block-1"],
  "metadata": {
    "role": "fixture"
  }
}
```

Transforms must use finite numeric triples, except `rotation_quat`, which must contain four finite
numbers. Scale values must be finite and greater than zero. Bounding boxes are optional, but when
present each `min` coordinate must be less than or equal to the matching `max` coordinate.

## Asset And Media References

Assets and media references are safe descriptors, not storage guarantees:

```json
{
  "id": "mesh-block-1",
  "role": "mesh",
  "mime_type": "model/gltf+json",
  "uri": "artifacts/block-1.gltf",
  "digest": "sha256:0123456789abcdef",
  "size_bytes": 2048,
  "local_only": false
}
```

Rules:

- `id`, `role`, and `digest` are required.
- `uri` is optional. If present in a public artifact, it must be relative or an `https` URL without
  userinfo, query strings, or fragments.
- Host-local absolute paths, `file://` URIs, loopback URLs, private-network URLs, and signed URLs
  are rejected from publishable artifacts.
- `local_only: true` may be used by a host run manifest to point at local retained assets, but
  issue-ready bundles must replace local paths with safe relative artifact paths or digests.
- `size_bytes` must be a non-negative integer when present.

## Provenance

`provenance` should be enough to reproduce or triage a scene artifact without console logs:

```json
{
  "runtime_manifest": "src/worldforge/providers/runtime_manifests/example-scene.json",
  "command": "worldforge-smoke-example-scene --input prompt.json",
  "input_digest": "sha256:input",
  "result_digest": "sha256:result",
  "event_count": 4,
  "limitations": [
    "fixture-only artifact",
    "does not certify physical validity"
  ]
}
```

The command may omit host-local absolute paths when preparing an issue-ready bundle. Runtime
versions, model names, and device labels are allowed when they are not secrets.

## Redaction Rules

Validators and issue-bundle exporters should reject or redact:

- bearer tokens, API keys, signed URL query strings, fragments, and userinfo;
- host-local absolute paths, home-directory paths, and `file://` URIs in publishable artifacts;
- provider metadata keys that contain secret-like terms such as `token`, `secret`, `key`, or
  `signature`;
- object instances, tuples, non-finite numbers, bytes, and other non-JSON-native values;
- oversized metadata that would hide runtime dumps, raw tensors, binary blobs, or unbounded logs.

Redaction must preserve enough context to triage the artifact: provider name, object IDs, asset
roles, safe URI path, digest, size, and failure reason.

## Host-Owned Responsibilities

Hosts own:

- installing and licensing 3D runtimes, GPU stacks, viewers, renderers, simulators, and conversion
  tools;
- downloading and retaining generated meshes, point clouds, Gaussian splats, textures, previews,
  camera paths, and checkpoints;
- converting provider-native outputs into the JSON scene artifact;
- validating downstream simulator, collision, physics, or robotics assumptions;
- deciding whether local-only evidence can be published.

WorldForge owns:

- the JSON-native artifact schema and validation helpers;
- provider-event redaction boundaries;
- fixture coverage for valid and malformed artifacts;
- docs that prevent scene artifacts from being presented as physical-fidelity evidence.

## Follow-Up Contract For #143

The follow-up fixture and validation issue can proceed without changing capability semantics.
It should add:

- one valid minimal scene artifact fixture;
- malformed transform, invalid unit, unsafe asset reference, non-finite numeric value, non-native
  metadata, and oversized metadata fixtures;
- validators that reject unsafe publishable artifacts in a clean checkout;
- docs showing how to attach sanitized scene artifacts to provider issues.

Until that lands, spatial and 3D scene providers remain deferred.
