# Conservative Hybrid Re-ID Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** Convert short ByteTrack fragments into conservative dancer identity clusters, pause target analysis for explicit user confirmation at ambiguous transitions, and resume safely without changing the Analysis Package v1 contract.

**Architecture:** Detection creates owner/job-private `TrackFragment` records and deterministic appearance/pose/time descriptors. `IdentityClusterer` auto-merges only high-confidence compatible fragments, returning a small cluster-based candidate list. After a target is selected, a persistent target work plan processes trusted fragments and pauses at an ambiguous fragment; the coordinator stores an `awaitingConfirmation` job plus one confirmation payload. The SwiftUI client fetches that payload, asks the user whether it is the same dancer, submits an idempotent decision, and resumes polling. Per-fragment pose output is checkpointed in the job workspace; the final ZIP is assembled only after all decisions are resolved.

**Tech Stack:** Python 3.11, OpenCV, existing RTMDet-m/RTMPose-m/ByteTrack-style tracker, FastAPI/Pydantic, atomic JSON repository, Swift 6/SwiftUI/Observation, Swift Testing, iPhone 17 Pro Max iOS 26.5.

## Scope and invariants

- Do not add a third-party Re-ID model, facial embeddings, cloud/GPU work, login work, or a new Analysis Package schema.
- `candidateId` remains the public stable identifier, but represents one identity cluster rather than one raw track.
- Keep the public state spelling `awaitingConfirmation`, matching the existing backend and iOS `AnalysisJobState`; the confirmation payload declares `kind: "identity"` so it is not confused with any future confirmation type.
- All images, descriptors, decisions, and checkpoints stay in `<workspace>/<owner>/<job>/analysis/`; no raw media, crops, vectors, token, or absolute path enters Git.
- A low-confidence or rejected segment must not receive pose, spotlight, or interpolated skeleton data. The player therefore falls back to its existing complete-frame mode for that interval.
- Candidate results are limited to the eight highest-ranked identity clusters. This prevents a fragmented 180-second video from presenting dozens of near-duplicate choices while retaining a deterministic ranking.

## Task 1: Deterministic identity fragments and conservative clusters

**Files:**
- Create: `backend/workers/analysis/stage_lab_analysis/identity.py`
- Modify: `backend/workers/analysis/stage_lab_analysis/tracking.py`
- Modify: `backend/workers/analysis/stage_lab_analysis/candidates.py`
- Modify: `backend/workers/analysis/stage_lab_analysis/worker.py`
- Create: `backend/workers/analysis/tests/test_identity.py`
- Modify: `backend/workers/analysis/tests/test_candidates.py`
- Modify: `backend/workers/analysis/tests/test_worker_detection.py`

### 1. Write the failing behavior tests

Add `test_identity.py` with synthetic `TrackFragment` fixtures. Assert all of the following before writing production code:

1. Two time-adjacent fragments with matching normalized HSV histogram, edge density, pose proportions, and plausible travel merge into one `IdentityCluster`.
2. Clearly different clothing/pose descriptors never merge, even if their boxes overlap in the same area.
3. Spatially impossible travel and overlapping time intervals are rejected before scoring.
4. A score in the confirm band returns `IdentityDecision.awaiting_confirmation`; it must not silently merge.
5. Empty/NaN descriptors return `IdentityDecision.reject` rather than a guessed identity.
6. Clustering order is deterministic when input tracks are reordered.

Extend `test_candidates.py` to prove that a cluster combines appearance intervals, uses its three temporally spread representative samples, returns a public `candidate-N` ID, and ranks only the best eight clusters. Extend `test_worker_detection.py` with a frame sequence where a dancer leaves, reappears with a compatible descriptor, and is returned as one candidate instead of two raw tracks.

### 2. Implement the minimal worker-only identity model

In `identity.py`, introduce immutable internal dataclasses:

```python
TrackDescriptor
TrackFragment
IdentityCluster
IdentityDecision
IdentityConfirmation
```

`TrackDescriptor` stores normalized HSV histogram bins, edge density, normalized shoulder/hip/torso ratios, pose quality, start/end center, estimated velocity, and validity. It contains only numeric feature values and never a face crop or embedding.

Add `TrackFragmentBuilder` that receives per-track frame samples from `AnalysisWorker`. It samples at most six full-body crops per finished track, computes the descriptor with OpenCV, and retains only the three representative image sources needed for later output. If pose is not available in detection, write `pose_quality=0` and omit pose ratios; similarity must still work from valid appearance/time data but require a stricter automatic threshold.

Add `ConservativeIdentityClusterer` with named, tested thresholds:

- `auto_merge_score >= 0.88`
- `confirmation_score >= 0.68 and < 0.88`
- reject below `0.68`, non-monotonic time, overlap, impossible travel, or invalid descriptors

Use weighted appearance (0.55), pose proportion (0.20 when valid), and temporal motion (0.25). Renormalize weights when pose is missing. Expose a pure `cluster(fragments)` result containing automatic clusters plus unresolved edges; do not make API or filesystem changes in this task.

Refactor `Candidate` in `candidates.py` from `track_id: int` to `fragment_ids: tuple[int, ...]`, retaining a `primary_fragment_id` property for representative selection. Make `CandidateExtractor.extract_clusters(...)` consume `IdentityCluster` objects, aggregate intervals/box/confidence, cap to eight, and keep `CandidateSet` public behavior unchanged.

Refactor `AnalysisWorker.detect_candidates` to collect frames for `tracker.all_tracks`, build fragments/descriptors, cluster them, and write representative crops from the selected cluster samples. Make the worker save a private `analysis/identity-clusters.json` artifact containing fragments, descriptors, clusters, and unresolved edges for the later target command. Its serialized schema is internal and versioned independently as `identitySchemaVersion: 1`.

### 3. Verify Task 1

Run:

```bash
cd /Users/garysmac/Documents/kpop翻跳
./scripts/verify-local-ai.sh
backend/.venv/bin/python -m pytest backend/workers/analysis/tests/test_identity.py backend/workers/analysis/tests/test_candidates.py backend/workers/analysis/tests/test_worker_detection.py -q
```

Expected: all worker tests pass; no API, iOS, cloud, or result ZIP member changes.

## Task 2: Checkpointed target analysis and confirmation-capable FastAPI state machine

**Files:**
- Modify: `backend/workers/analysis/stage_lab_analysis/worker.py`
- Modify: `backend/workers/analysis/stage_lab_analysis/worker_cli.py`
- Modify: `backend/api/app/ports/analysis_runner.py`
- Modify: `backend/api/app/adapters/analysis/local_analysis_runner.py`
- Modify: `backend/api/app/schemas/analysis.py`
- Modify: `backend/api/app/adapters/repositories/file_analysis_repository.py`
- Modify: `backend/api/app/services/analysis_coordinator.py`
- Modify: `backend/api/app/routes/analysis.py`
- Create: `backend/tests/unit/test_identity_confirmation.py`
- Modify: `backend/tests/unit/test_analysis_coordinator.py`
- Modify: `backend/tests/smoke/test_local_ai_real_chain.py`

### 1. Write failing API and recovery tests

Add tests that establish these contracts before implementation:

1. A selected cluster with a confirmation-band transition makes the runner return a pending identity confirmation, moves the job from `analyzing` to `awaitingConfirmation`, and does not create `result-metadata.json`.
2. `GET /v1/jobs/{job}/identity-confirmation` returns exactly the current owner/job payload and returns the same not-found response for another owner.
3. `POST /v1/jobs/{job}/identity-confirmation` accepts only the pending `confirmationId`, one of `same`/`different`, and an `Idempotency-Key`; duplicate equal requests are successful, a reused key for another decision is `409`, and stale IDs are `409`.
4. `same` resumes target work and includes the accepted fragment in pose output. `different` marks that fragment excluded and ensures its time range has no spotlight/pose sample.
5. A process restart retains `target-work-plan.json`, the pending confirmation, completed per-fragment pose checkpoint files, and does not re-run completed fragments.
6. `resume_pending()` intentionally leaves `awaitingConfirmation` paused. It resumes only `queued`/`analyzing` jobs after a decision transitions them back to `queued`.
7. Existing target selection idempotency and job owner isolation tests continue to pass.

### 2. Add the persistent worker outcome and checkpoint protocol

In `worker.py`, replace the single success-only target return with a tagged internal outcome:

```python
TargetAnalysisCompleted(result: TargetAnalysis)
TargetAnalysisAwaitingConfirmation(confirmation: IdentityConfirmation)
```

When target analysis begins, load the `identity-clusters.json` produced by detection and create `analysis/target-work-plan.json` atomically if absent. The plan contains `candidateId`, ordered accepted fragments, rejected fragments, pending confirmation ID (if any), and `nextFragmentIndex`.

Process fragments in chronological order. For each automatically accepted fragment, write its RTMPose result as `analysis/target-checkpoints/<fragment-id>.json` atomically and advance `nextFragmentIndex`. Before a confirmation-band fragment, write the pending confirmation and return `TargetAnalysisAwaitingConfirmation`; do not estimate it, interpolate across it, or write later fragments. On subsequent invocation, load the plan and checkpoints, skip completed fragments, and continue from `nextFragmentIndex`.

The pending confirmation records `confirmationId`, `previousImagePath`, `candidateImagePath`, `previousInterval`, `candidateInterval`, and the candidate cluster ID. Use existing job-scoped `analysis/candidates/...jpg` content paths. If either representative is missing, produce a recoverable worker error rather than returning an unsafe confirmation.

On a stored `same` decision, add the fragment to the selected cluster path and process it. On `different`, add it to excluded fragments and advance without pose. When the plan is exhausted, load all per-fragment checkpoints, concatenate and validate monotonically, create the existing `result-v1.zip`, and keep its five v1 members unchanged.

Update `worker_cli.py` so `target` emits either `{ "outcome": "awaitingConfirmation", "confirmation": ... }` or `{ "outcome": "completed", "result": ... }`. It must not print worker diagnostics to stdout.

### 3. Add API DTOs, persistence, and transitions

In `schemas/analysis.py`, add:

```python
IdentityDecisionValue = Literal["same", "different"]
IdentityConfirmationResponse
SubmitIdentityConfirmationRequest
```

Keep `AnalysisJobState.AWAITING_CONFIRMATION = "awaitingConfirmation"`; do not introduce a second state spelling.

Extend `FileAnalysisRepository` with atomic owner/job-scoped `set_identity_confirmation`, `identity_confirmation`, `set_identity_decision`, and `identity_decision` methods. Persist `identity-confirmation.json`, `identity-decision.json`, and `target-work-plan.json` only under the existing analysis directory. Make a final decision immutable except for an idempotent replay of the exact same key/payload.

Change `AnalysisRunner.analyze_target` and `LocalAnalysisRunner.analyze_target` to return the tagged outcome. In `AnalysisCoordinator._analyze`, store the pending payload and set `awaitingConfirmation` when required; otherwise preserve the current result-ready path. Add `identity_confirmation(...)` and `submit_identity_confirmation(...)` coordinator methods. A successful decision clears the current pending payload, changes the job to `queued` at its current progress, and schedules the runner. Do not schedule analysis from `resume_pending()` while it is awaiting confirmation.

Expose protected endpoints in `routes/analysis.py`:

```text
GET  /v1/jobs/{job_id}/identity-confirmation
POST /v1/jobs/{job_id}/identity-confirmation
```

Both use `authenticated_user`, the existing idempotency dependency, and identical owner-not-found behavior. Add route tests for authorization and malformed identifiers.

### 4. Verify Task 2

Run:

```bash
cd /Users/garysmac/Documents/kpop翻跳
./scripts/verify-local-ai.sh
./scripts/verify-backend.sh
backend/.venv/bin/python -m pytest backend/tests/unit/test_identity_confirmation.py backend/tests/unit/test_analysis_coordinator.py backend/tests/smoke/test_local_ai_real_chain.py -q
```

Expected: all targeted and full backend gates pass. The smoke test has a deterministic synthetic confirmation fixture as well as its existing real-media optional path; it must never put sample media in the repository.

## Task 3: iOS confirmation client, polling state, and user decision screen

**Files:**
- Modify: `kpop/Core/Networking/AnalysisAPIClient.swift`
- Modify: `kpop/Core/Services/AnalysisService.swift`
- Modify: `kpop/Core/Services/RemoteAnalysisService.swift`
- Modify: `kpop/Views/RealAnalysisModel.swift`
- Modify: `kpop/Views/DancerPickView.swift`
- Create: `kpop/Views/IdentityConfirmationView.swift`
- Modify: `kpopTests/AnalysisAPIClientTests.swift`
- Modify: `kpopTests/RemoteAnalysisServiceTests.swift`
- Modify: `kpopTests/RealAnalysisModelTests.swift`
- Create: `kpopUITests/IdentityConfirmationFlowUITests.swift`

### 1. Write failing Swift tests

Add DTO decoding/encoding tests for the confirmation payload, protected image content paths, and the `same`/`different` request body plus stable idempotency keys. Add service tests proving backend `awaitingConfirmation` does not map to generic analyzing state.

Extend `RealAnalysisModelTests` with a scripted sequence:

1. selected target returns `awaitingConfirmation`;
2. model loads the confirmation exactly once and exposes it in state;
3. `same` submits one stable request then returns to polling;
4. `different` also resumes polling;
5. cancellation/transport failure leaves the model recoverably retryable without falsely advancing the project phase.

Add one UI launch test using a fake `AnalysisService` that opens the confirmation screen, checks both images/placeholders and both choices, and verifies the controls have accessibility identifiers. Do not use a real token, video, or FastAPI process in UI tests.

### 2. Implement the API and state mapping

In `AnalysisAPIClient.swift`, add Codable `IdentityConfirmationDTO` and calls:

```swift
func identityConfirmation(jobID: UUID) async throws -> IdentityConfirmationDTO
func submitIdentityConfirmation(jobID: UUID, confirmationID: String, decision: IdentityDecisionValue, idempotencyKey: String) async throws -> RemoteJob
```

Validate both image paths through the existing `contentURL(jobID:relativePath:)` before exposing them. Reuse bearer/pairing headers and existing API error decoding.

Extend `AnalysisService` and `RemoteAnalysisService` with a domain `IdentityConfirmation` value plus `identityConfirmation(jobID:)` and `submitIdentityConfirmation(...)`. Generate a deterministic decision key from job ID, confirmation ID, and decision. Do not persist any token, image bytes, or external URL in SwiftData.

Change `RealAnalysisState` to add `case awaitingIdentityConfirmation(IdentityConfirmation)`. In `RealAnalysisModel.poll`, when status is `.awaitingConfirmation`, fetch the confirmation once, publish that state, and return instead of endless polling. Add `confirmIdentity(_:project:)` that submits the answer and restarts polling; leave `DanceProject.phase` as `.analyzing` until a real `resultReady` package is imported.

### 3. Implement the focused SwiftUI confirmation presentation

Create `IdentityConfirmationView` as a sheet or destination presented by `DancerPickView` when the model is awaiting confirmation. It presents:

- the title `是否仍是所选舞者？`;
- previous and candidate frame crops fetched only through `AuthenticatedCandidateImage`-style authenticated content loading;
- their human-readable time ranges;
- a plain explanation that choosing “不是” keeps this interval as complete frame and does not re-run upload;
- primary `是，同一位舞者` and secondary `不是` buttons, disabled only during submission;
- a retryable error state with no automatic decision.

Use `identity-confirmation-same` and `identity-confirmation-different` accessibility identifiers. Keep the existing two-column candidate picker and all iPhone 17 Pro Max portrait practice work unchanged.

### 4. Verify Task 3

Run the project’s established iOS gate from the repository root:

```bash
cd /Users/garysmac/Documents/kpop翻跳
./scripts/verify-ios.sh
```

If CoreSimulator/Xcode fails independently of the changed tests, record the exact command, exit code, and system failure in `docs/KNOWN_ISSUES.md`; do not mark the task passed on a build-only inference.

## Task 4: Real local acceptance, documentation, and release gate

**Files:**
- Modify: `backend/tests/smoke/test_local_ai_real_chain.py`
- Modify: `docs/ai/ACCEPTANCE_2026-07-21.md`
- Modify: `docs/PROJECT_STATUS.md`
- Modify: `docs/KNOWN_ISSUES.md` if an unresolved environment or visual limitation remains
- Modify: `README.md` only if the local test/confirmation workflow changes user-facing setup

### 1. Add reproducible acceptance checks

Extend the real smoke harness to emit only non-sensitive metrics: elapsed time, candidate cluster count, selected candidate visible duration, accepted/rejected/awaiting fragment counts, package member list, and final pose coverage. It must accept `STAGE_LAB_ACCEPTANCE_VIDEO`; when unset it skips with an explicit reason.

Run the supplied `Hype Boy` source only from its local ignored path. Verify:

1. candidates are identity clusters, capped at eight, rather than the prior 64 raw fragments;
2. at least one selected dancer cluster reaches 80% of its measurable visible duration through accepted segments;
3. every ambiguous boundary produces `awaitingConfirmation` and never emits a cross-boundary spotlight path;
4. a scripted `same` and `different` decision each reach a valid v1 ZIP;
5. the ZIP still has only `manifest.json`, `pose-track.json`, `spotlight-track.json`, `timeline.json`, and `confidence.json`;
6. manually in Xcode on iPhone 17 Pro Max iOS 26.5, the confirmation screen shows private crops, `same` resumes tracking, and `different` visibly uses complete-frame fallback in that interval.

### 2. Update durable records and final gates

Record actual commands, dates, durations, pass/fail counts, environment, and the distinction between automated local smoke, Simulator tests, and manual device visuals in `docs/ai/ACCEPTANCE_2026-07-21.md`. Update `docs/PROJECT_STATUS.md` at every completed task, changing the current Re-ID entry from implementation planning to in-progress, then to pending acceptance only after all gates pass.

Run:

```bash
cd /Users/garysmac/Documents/kpop翻跳
./scripts/verify-local-ai.sh
./scripts/verify-backend.sh
./scripts/verify-ios.sh
STAGE_LAB_ACCEPTANCE_VIDEO='/absolute/local/ignored/video.mp4' \
  backend/.venv/bin/python -m pytest backend/tests/smoke/test_local_ai_real_chain.py -q
git diff --check
```

Do not push or merge media, result archives, tokens, `.local-ai/`, `backend/.venv/`, or workspace output. Open a reviewable GitHub PR only when the applicable automated gates pass and the documentation distinguishes any unexecuted manual device step.

## Task ordering and acceptance checkpoints

1. Task 1 is worker-only and must be merged/accepted before API state changes.
2. Task 2 depends on Task 1 because it persists the cluster and work-plan format.
3. Task 3 depends on Task 2 because the UI consumes the finalized confirmation API.
4. Task 4 depends on Tasks 1-3 and is the only task allowed to claim the Re-ID feature is ready for user acceptance.

Each task is a separate branch/PR with its tests and `PROJECT_STATUS` update. No task enables cloud processing or user login.
