# Stage 1 Fancam Component Scorecard

Only aggregate benchmark results belong in this document. Do not record source
paths, frames, crops, embeddings, anonymous truth labels, observation details,
credentials, or rendered media.

| Candidate | Provenance / license | CPU evidence | Aggregate result | Selection |
| --- | --- | --- | --- | --- |
| current-baseline (RTMDet-m + OpenVINO 0277 + existing tracker) | Hash-gated `backend/workers/analysis/model-manifest.json`; Apache-2.0 | 2026-08-18 local CPU probe: detector + Re-ID ready | Not run against local 30–50 scene truth | `no_safe_candidate` |

## Selection gate

A candidate is selectable only when its supply chain review and CPU probe pass,
it has zero false locks, detection recall and identity accuracy are each at
least 0.95, and confirmation requests are no more than one per labelled minute.
If any evidence is missing, selection remains `no_safe_candidate`.
