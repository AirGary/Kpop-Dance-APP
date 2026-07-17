# Stage 6 Local Real AI Vertical Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Analyze one real group-dance video on the development Mac, let the user choose one detected dancer, and render real spotlight, skeleton, confidence, difficulty, repeat-group, and action-timeline results in the iOS practice player.

**Architecture:** Add an isolated Python 3.11 analysis worker beside the existing FastAPI app. A local-only coordinator promotes a completed upload into a persistent job workspace, runs candidate detection first, waits for target selection, runs target pose and timeline analysis second, then serves a versioned ZIP package that Swift validates and stores atomically. Existing cloud adapters and Fake analysis remain unchanged.

**Tech Stack:** Python 3.11, FastAPI, Pydantic, FFprobe/FFmpeg, PyTorch, MMDetection RTMDet-m, MMDetection ByteTrack, MMPose RTMPose-m, librosa, NumPy, pytest, SwiftUI, SwiftData, AVFoundation, Swift Testing.

## Global Constraints

- The first acceptance video is the existing `82MAJOR Trophy` practice-room video; it is not committed to Git.
- Input is MP4, MOV, or M4V, at most 6 minutes and 2 GiB; the original video is never modified.
- The analysis proxy is at most 720p and 30 fps and never upscales lower-quality input.
- Only the selected dancer receives full pose analysis.
- Music analysis is limited to BPM, beats, and downbeat-like strong beats; no verse, chorus, bridge, or Dance Break labels.
- Result coordinates are normalized to `0...1`; timestamps are monotonic seconds on the source-video time base.
- Local inference prefers MPS only after a real probe passes and falls back once to CPU; repeated backend guessing is forbidden.
- No Sign in with Apple, user-facing account flow, Google Cloud GPU, cloud deployment, APNs, CloudKit, StoreKit, or new paid service enters this plan.
- The real-analysis entry point must never present fixed Fake candidates or sample timeline nodes as model output.
- Existing Cloud Run, Firestore, Storage, Terraform, upload, Preview, and Fake-analysis behavior must remain regression-tested.
- Model code, weights, and transitive dependencies require recorded source, version, checksum, and license before use.
- The baseline model combination is RTMDet-m + ByteTrack + RTMPose-m. Detector, tracker, and pose estimator remain replaceable behind protocols, while Analysis Package schema v1 remains model-independent.
- VideoMAE and general video-language models do not replace frame-by-frame detection, identity tracking, or target pose estimation in the first demo.

---

### Task 1: Establish The Reproducible AI Runtime Gate

**Files:**
- Create: `backend/workers/analysis/pyproject.toml`
- Create: `backend/workers/analysis/stage_lab_analysis/runtime_probe.py`
- Create: `backend/workers/analysis/tests/test_runtime_probe.py`
- Create: `backend/workers/analysis/model-manifest.json`
- Create: `scripts/bootstrap-local-ai.sh`
- Create: `scripts/verify-local-ai.sh`
- Modify: `.gitignore`
- Modify: `backend/README.md`
- Modify: `docs/PROJECT_STATUS.md`

**Interfaces:**
- Produces: `RuntimeCapabilities(device: Literal["mps", "cpu"], detector_ready: bool, pose_ready: bool, ffmpeg_version: str)`.
- Produces: `.local-ai/venv/bin/python`, `.local-ai/models/`, and `.local-ai/runtime-capabilities.json`, all ignored by Git.
- Consumes: official RTMDet-m person-detector and RTMPose-m body checkpoints listed in `model-manifest.json`.

- [ ] **Step 1: Write the runtime and manifest contract tests**

Add tests that require Python `3.11.x`, reject a model manifest without `name`, `sourceUrl`, `sha256`, `license`, and `licenseUrl`, and verify `choose_device()` selects `mps` only when a one-frame detector and pose probe both pass; otherwise it selects `cpu` exactly once.

- [ ] **Step 2: Run the focused tests and observe the missing worker failure**

Run:

```bash
backend/.venv/bin/python -m pytest backend/workers/analysis/tests/test_runtime_probe.py -q
```

Expected: collection fails because `stage_lab_analysis.runtime_probe` does not exist.

- [ ] **Step 3: Add the isolated worker project and bootstrap script**

Use a Python 3.11 virtual environment separate from `backend/.venv`. The bootstrap script must fail with an actionable message when `python3.11`, `ffmpeg`, or `ffprobe` is absent; it may print the exact Homebrew commands `brew install python@3.11 ffmpeg`, but must not install software without approval. Declare compatible dependency ranges in `pyproject.toml`, install them, then write an exact `pip freeze` lock to `.local-ai/requirements.lock` for evidence without committing platform-specific wheel paths.

The probe must:

```python
@dataclass(frozen=True, slots=True)
class RuntimeCapabilities:
    device: Literal["mps", "cpu"]
    detector_ready: bool
    pose_ready: bool
    ffmpeg_version: str
```

Load the official RTMDet-m detector checkpoint and RTMPose-m pose checkpoint, run both against a generated non-user test frame, attempt MPS once, and retry on CPU only when the failure is classified as an unsupported MPS operator or backend initialization error.

- [ ] **Step 4: Record model provenance and verify licenses**

Record the exact official OpenMMLab URLs and SHA-256 values after download. Record Apache-2.0 for MMDetection and MMPose and the license metadata shipped with each selected checkpoint. Do not proceed if a checkpoint or dependency is marked non-commercial, unknown, or checksum-mismatched.

- [ ] **Step 5: Run the real single-frame gate**

Run:

```bash
./scripts/bootstrap-local-ai.sh
./scripts/verify-local-ai.sh
```

Expected: FFmpeg and FFprobe versions are reported; detector and pose each return at least one valid tensor result; `.local-ai/runtime-capabilities.json` names either `mps` or `cpu`. If neither backend passes, mark Stage 6 blocked and do not start Task 2.

- [ ] **Step 6: Run existing backend verification**

Run `./scripts/verify-backend.sh`. Expected: all existing tests pass and no AI dependencies are installed into the Cloud Run API environment.

- [ ] **Step 7: Update evidence and commit**

Record Python, FFmpeg, model versions, device, elapsed probe time, checksums, and license result in `docs/PROJECT_STATUS.md` and `backend/README.md`.

```bash
git add .gitignore backend/workers/analysis scripts/bootstrap-local-ai.sh scripts/verify-local-ai.sh backend/README.md docs/PROJECT_STATUS.md
git commit -m "build: establish local AI runtime gate"
```

### Task 2: Define Persistent Analysis Contracts And Workspace

**Files:**
- Create: `backend/api/app/schemas/analysis.py`
- Create: `backend/api/app/ports/analysis_repository.py`
- Create: `backend/api/app/adapters/repositories/file_analysis_repository.py`
- Create: `backend/api/app/ports/analysis_workspace.py`
- Create: `backend/api/app/adapters/storage/local_analysis_workspace.py`
- Create: `backend/tests/unit/test_file_analysis_repository.py`
- Create: `backend/tests/unit/test_local_analysis_workspace.py`
- Create: `backend/contracts/fixtures/dancers.json`
- Create: `backend/contracts/fixtures/analysis-result.json`
- Modify: `backend/api/app/schemas/jobs.py`
- Modify: `backend/api/app/ports/job_repository.py`
- Modify: `backend/api/app/adapters/repositories/in_memory_job_repository.py`
- Modify: `backend/api/app/adapters/repositories/firestore_job_repository.py`
- Modify: `backend/tests/contracts/test_contracts.py`

**Interfaces:**
- Produces: `AnalysisJobState`, `DancerCandidateResponse`, `SelectTargetRequest`, `AnalysisResultResponse`, `AnalysisErrorDetail`.
- Produces: `AnalysisRepository.load/update/candidates/set_candidates/set_result` with owner-isolated UUID lookup.
- Produces: workspace paths under `<OBJECT_STORAGE_ROOT>/<owner>/<job>/analysis/`.
- Consumes: existing `JobResponse`, `JobRepository`, upload UUID, owner ID, and job ID.

- [ ] **Step 1: Write failing schema and persistence tests**

Require all Swift state raw values (`draft`, `preparing`, `uploading`, `uploaded`, `detecting`, `awaitingTarget`, `queued`, `analyzing`, `awaitingConfirmation`, `resultReady`, `importing`, `completed`, `failedRecoverable`, `failedTerminal`, `cancelling`, `deleted`). Require candidate IDs, three representative-image paths, appearance intervals, normalized box summary, and confidence in `0...1`. Require result metadata with schema version `1`, SHA-256, byte count, and authenticated content path.

Test that repository writes use temporary-file plus atomic replace, survive a new repository instance, hide foreign owners behind the same not-found error, and reject path traversal. Test that the workspace promotes the completed local upload into the job directory using hard-link when possible and copy fallback without modifying the source.

- [ ] **Step 2: Confirm contract failures**

Run:

```bash
backend/.venv/bin/python -m pytest \
  backend/tests/unit/test_file_analysis_repository.py \
  backend/tests/unit/test_local_analysis_workspace.py \
  backend/tests/contracts/test_contracts.py -q
```

Expected: failures for missing schemas, repository, workspace, and fixtures.

- [ ] **Step 3: Implement stable DTOs and immutable path rules**

Use Pydantic aliases matching Swift JSON. Extend `JobResponse.state` from `Literal["draft"]` to the exact state union and preserve default `draft`. Add `JobRepository.update_response(expected_state, response) -> JobRecord` to both in-memory and Firestore adapters so worker state transitions use compare-and-set semantics rather than blind writes.

- [ ] **Step 4: Implement the persistent analysis repository and workspace**

Store `analysis-state.json`, candidates, proxy, checkpoints, and result below the owner/job workspace. Never expose absolute paths in API DTOs. A second process instance must load `analysis-state.json` and continue from `uploaded`, `detecting`, `awaitingTarget`, `queued`, `analyzing`, or `resultReady` without re-importing the source.

- [ ] **Step 5: Run focused and regression tests**

Run the focused command from Step 2 and `./scripts/verify-backend.sh`. Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/api/app/schemas backend/api/app/ports backend/api/app/adapters backend/tests backend/contracts
git commit -m "feat: persist local analysis jobs"
```

### Task 3: Implement Deterministic Media Preflight And Proxy Generation

**Files:**
- Create: `backend/workers/analysis/stage_lab_analysis/media.py`
- Create: `backend/workers/analysis/stage_lab_analysis/errors.py`
- Create: `backend/workers/analysis/tests/test_media.py`
- Create: `backend/workers/analysis/tests/fixtures/generate_media_fixtures.sh`
- Modify: `scripts/verify-local-ai.sh`

**Interfaces:**
- Produces: `MediaReport(duration_seconds, width, height, fps, rotation_degrees, video_codec, has_audio)`.
- Produces: `create_proxy(source: Path, destination: Path) -> MediaReport`.
- Produces stable errors: `media_corrupt`, `video_track_missing`, `duration_exceeded`, `codec_unsupported`, `file_size_exceeded`, `ffmpeg_failed`. `file_size_exceeded` was added during Task 3 implementation as the explicit result for the existing 2 GiB input limit.

- [ ] **Step 1: Generate legal synthetic fixtures and write failing tests**

Generate short color/test-pattern fixtures with FFmpeg: 4K60 H.264, 540p24 H.264, rotated MOV, audio-less MP4, audio-only M4A, corrupt bytes, and a metadata-only duration-over-limit fixture. Tests must not depend on the user's dance video.

- [ ] **Step 2: Verify tests fail before implementation**

Run `.local-ai/venv/bin/python -m pytest backend/workers/analysis/tests/test_media.py -q`. Expected: import failure for `stage_lab_analysis.media`.

- [ ] **Step 3: Implement strict FFprobe parsing**

Invoke FFprobe without shell interpolation, parse JSON, reject missing/invalid fields, normalize rational frame rates, and map rotation metadata. Do not include source paths or filenames in raised user-visible messages.

- [ ] **Step 4: Implement the only-downscale proxy command**

Build an argv array that scales only when width or height exceeds the 720p long-edge policy, caps frame rate at 30 only when higher, fixes timestamps from zero, uses H.264/yuv420p, and copies or omits audio only as required by analysis. Verify 540p24 remains 540p24 and 4K60 becomes at most 720p30.

- [ ] **Step 5: Run media and full worker tests**

Run `.local-ai/venv/bin/python -m pytest backend/workers/analysis/tests -q` and `./scripts/verify-local-ai.sh`. Expected: all pass with no user files read.

- [ ] **Step 6: Commit**

```bash
git add backend/workers/analysis scripts/verify-local-ai.sh
git commit -m "feat: add AI media preflight"
```

### Task 4: Generate Real Dancer Candidates With RTMDet-m And ByteTrack

**Files:**
- Create: `backend/workers/analysis/stage_lab_analysis/detection.py`
- Create: `backend/workers/analysis/stage_lab_analysis/tracking.py`
- Create: `backend/workers/analysis/stage_lab_analysis/candidates.py`
- Create: `backend/workers/analysis/stage_lab_analysis/worker.py`
- Create: `backend/workers/analysis/tests/test_tracking.py`
- Create: `backend/workers/analysis/tests/test_candidates.py`
- Create: `backend/workers/analysis/tests/test_worker_detection.py`

**Interfaces:**
- Consumes: proxy video and runtime capabilities from Tasks 1 and 3.
- Produces: `Detection(time_seconds, box, confidence)` and `Track(track_id, samples)`.
- Produces: `CandidateSet` plus three JPEG representative images per accepted track.
- Produces: `AnalysisWorker.detect_candidates(workspace: Path) -> CandidateSet`.

- [x] **Step 1: Write tracker and candidate-ranking tests**

Use synthetic detection sequences to verify ByteTrack association across short occlusion, monotonic time, normalized boxes, no cross-frame duplicate track assignment, and deterministic ranking by visible duration, median area, full-body proxy score, and stability. Reject tracks shorter than the configured minimum visible duration.

- [x] **Step 2: Run tests and confirm missing implementation failures**

Run `.local-ai/venv/bin/python -m pytest backend/workers/analysis/tests/test_tracking.py backend/workers/analysis/tests/test_candidates.py backend/workers/analysis/tests/test_worker_detection.py -q`.

- [x] **Step 3: Wrap RTMDet-m behind a narrow detector adapter**

The `PersonDetector` adapter uses RTMDet-m by default, accepts RGB frames, and returns person-class boxes only. It owns preprocessing, device selection, thresholding, and model version reporting; downstream code must not import MMDetection tensors. On an MPS runtime error, recreate the model on CPU once and continue from the latest frame checkpoint. A future detector may replace RTMDet-m only by implementing the same adapter contract.

- [x] **Step 4: Implement ByteTrack and candidate extraction**

Use MMDetection's Apache-2.0 ByteTrack implementation behind a `PersonTracker` adapter and persist tracker checkpoints at bounded frame intervals. Representative frames must be selected from high-confidence, temporally separated samples and cropped with safe padding. Strip image metadata and use generated candidate IDs independent of model-internal track IDs.

- [x] **Step 5: Run a real detection-only sample gate**

Run the worker against the user-selected `82MAJOR Trophy` file supplied via an ignored environment variable `STAGE_LAB_ACCEPTANCE_VIDEO`. Record only candidate count, elapsed time, device, and anonymized track metrics; do not copy the video or candidate images into Git or logs. Expected: at least three stable candidates with valid representative images. If this fails, tune thresholds against this single video and record each measured change rather than switching models randomly. The candidate preflight uses a configurable six-frame sampling stride on CPU; target analysis must not assume this lower rate.

- [x] **Step 6: Run worker regression and commit**

Run all worker tests and `./scripts/verify-local-ai.sh`.

```bash
git add backend/workers/analysis
git commit -m "feat: detect real dancer candidates"
```

### Task 5: Orchestrate Two-Stage Analysis Through FastAPI

**Files:**
- Create: `backend/api/app/ports/analysis_runner.py`
- Create: `backend/api/app/adapters/analysis/local_analysis_runner.py`
- Create: `backend/api/app/services/analysis_coordinator.py`
- Create: `backend/api/app/routes/analysis.py`
- Create: `backend/tests/unit/test_analysis_coordinator.py`
- Create: `backend/tests/api/test_analysis_routes.py`
- Modify: `backend/api/app/container.py`
- Modify: `backend/api/app/main.py`
- Modify: `backend/api/app/services/upload_service.py`
- Modify: `backend/api/app/routes/jobs.py`
- Modify: `backend/tests/contracts/test_openapi.py`
- Modify: `backend/README.md`

**Interfaces:**
- Produces: `GET /v1/jobs/{job_id}/dancers`.
- Produces: `POST /v1/jobs/{job_id}/target` with `{"candidateId":"..."}` and `Idempotency-Key`.
- Produces: `GET /v1/jobs/{job_id}/result` and authenticated `GET /v1/jobs/{job_id}/result/content`.
- Produces: `AnalysisCoordinator.on_upload_completed`, `resume_pending`, `select_target`, and `shutdown`.
- Consumes: persistent repository/workspace, local runner, and completed upload callback.

- [x] **Step 1: Write failing coordinator state-machine tests**

Test `uploaded -> detecting -> awaitingTarget`, `awaitingTarget -> queued -> analyzing -> resultReady`, idempotent target selection, foreign-owner `404`, invalid candidate `422`, runner failure to `failedRecoverable`, unsupported input to `failedTerminal`, and restart resume from each checkpoint. Assert that duplicate completion or selection never starts two worker processes.

- [x] **Step 2: Write failing API and OpenAPI contract tests**

Require the four endpoints above, stable error envelopes, authorization on result bytes, no absolute paths in JSON, and `409` for an idempotency key reused with a different candidate.

- [x] **Step 3: Implement a subprocess runner with bounded output**

Launch `.local-ai/venv/bin/python -m stage_lab_analysis.worker` with workspace-relative arguments, capture only structured status JSON, cap stderr retained for diagnostics, support cancellation, and never log source names or paths. The runner must not run inside Cloud Run containers.

- [x] **Step 4: Wire local AI mode without weakening cloud auth**

Add `APP_ENVIRONMENT=local-ai`. It uses development bearer verification, local resumable uploads, persistent analysis state, and the local runner. Existing `development`, `cloud-bootstrap`, and `cloud` behavior must remain unchanged. Upload completion promotes the source and schedules candidate detection only in `local-ai` mode.

- [x] **Step 5: Add lifecycle resume and shutdown**

FastAPI lifespan calls `resume_pending()` after upload cleanup and awaits `shutdown()` on exit. Running tasks receive cancellation; completed checkpoints stay on disk for the next launch.

- [x] **Step 6: Run API, backend, and privacy tests**

Run focused tests, `./scripts/verify-backend.sh`, and assert request logs contain no bearer token, pairing token, source path, video title, candidate image, or result download bytes.

- [x] **Step 7: Commit**

Task 5 的真实候选联调已通过；目标姿态与结果生成仍明确属于 Task 7。

```bash
git add backend/api backend/tests backend/README.md
git commit -m "feat: orchestrate local AI analysis"
```

### Task 6: Connect Real Analysis State And Candidate Selection In iOS

**Files:**
- Create: `kpop/Core/Networking/AnalysisAPIClient.swift`
- Create: `kpop/Core/Services/RemoteAnalysisService.swift`
- Create: `kpop/Views/RealAnalysisModel.swift`
- Create: `kpopTests/AnalysisAPIClientTests.swift`
- Create: `kpopTests/RemoteAnalysisServiceTests.swift`
- Create: `kpopTests/RealAnalysisModelTests.swift`
- Modify: `kpop/App/JobsAPIConfiguration.swift`
- Modify: `kpop/kpopApp.swift`
- Modify: `kpop/Views/AnalysisPlaceholderView.swift`
- Modify: `kpop/Views/DancerPickView.swift`
- Modify: `kpop/Models/DanceProject.swift`

**Interfaces:**
- Produces: Swift DTOs matching `DancerCandidateResponse`, `SelectTargetRequest`, and `AnalysisResultResponse` exactly.
- Produces: `RemoteAnalysisService: AnalysisService` backed by HTTP.
- Produces: observable UI states for polling, real candidates, selection, retry, and result readiness.
- Consumes: the Stage 5 upload-created `remoteJobId` and Stage 6 endpoints.

- [x] **Step 1: Write failing JSON and request tests**

Verify paths, methods, bearer headers, idempotency keys, fractional timestamps, candidate arrays, result metadata, backend error mapping, cancellation, and that candidate image requests cannot escape the configured API origin.

- [x] **Step 2: Write failing UI model tests**

Test polling from `detecting` to `awaitingTarget`, no navigation before candidates exist, deterministic selection idempotency key, retry after recoverable failure, and result-ready transition. Fake services remain injectable and explicitly labeled Demo.

- [x] **Step 3: Implement environment configuration**

Simulator defaults to `127.0.0.1:8000`. A real-device Debug scheme may inject `STAGE_LAB_API_BASE_URL` and a short-lived pairing token at launch. Release and Staging must reject HTTP local-AI configuration. Never hard-code a LAN IP or pairing token.

- [x] **Step 4: Replace fixed analysis actions only in real mode**

The real analysis screen polls the actual job; it cannot expose “完成分析，选择舞者” as a manual state skip. The picker renders representative images and confidence from the server. Keep static candidates only in Preview/Fake mode with a visible Demo badge.

- [x] **Step 5: Persist cloud/local analysis metadata safely**

Add migration-safe optional fields for selected candidate ID, package checksum, and package byte count. Do not store candidate image bytes in SwiftData.

- [ ] **[in progress] Step 6: Run iOS verification and commit**

Run `./scripts/verify-ios.sh`. Expected: unit tests, cold-start UI test, Staging build, and Release build pass.

```bash
git add kpop kpopTests
git commit -m "feat: connect real dancer selection"
```

### Task 7: Produce RTMPose-m, Beat, Difficulty, Repeat, And Package Results

**Files:**
- Create: `backend/workers/analysis/stage_lab_analysis/pose.py`
- Create: `backend/workers/analysis/stage_lab_analysis/audio.py`
- Create: `backend/workers/analysis/stage_lab_analysis/timeline.py`
- Create: `backend/workers/analysis/stage_lab_analysis/package.py`
- Create: `backend/workers/analysis/tests/test_pose.py`
- Create: `backend/workers/analysis/tests/test_audio.py`
- Create: `backend/workers/analysis/tests/test_timeline.py`
- Create: `backend/workers/analysis/tests/test_package.py`
- Modify: `backend/workers/analysis/stage_lab_analysis/worker.py`
- Modify: `backend/workers/analysis/pyproject.toml`

**Interfaces:**
- Consumes: selected candidate track, proxy, source time base, and runtime capabilities.
- Produces: normalized `SpotlightKeyframe`, `PoseFrame`, `ConfidenceInterval`, `PracticeSegment`, and `RepeatGroup` records.
- Produces: `result-v1.zip` with `manifest.json`, `spotlight-track.json`, `pose-track.json`, `timeline.json`, and `confidence.json`.

- [ ] **Step 1: Write failing pose and package invariant tests**

Require monotonic timestamps, `0...1` coordinates, finite numbers, known skeleton topology version, joint confidence in `0...1`, no strong spotlight during low-confidence identity intervals, ZIP path safety, exact required members, per-member hashes, outer SHA-256, and deterministic JSON key ordering.

- [ ] **Step 2: Write failing timeline rule tests**

Use synthetic pose sequences to verify speed peaks, direction changes, displacement, pauses, minimum/maximum segment duration, beat snapping bounded to a defined tolerance, repeat grouping by normalized feature distance, easy/medium/hard reasons, and no-audio fallback. Require at least one human-readable reason for medium or hard segments.

- [ ] **Step 3: Implement the RTMPose-m adapter and confidence rules**

The `PoseEstimator` adapter uses RTMPose-m by default. Crop only the selected dancer with safe padding, map keypoints back to normalized full-frame coordinates, checkpoint at bounded intervals, and use the same one-time MPS-to-CPU fallback policy as detection. Preserve all-person boxes only for identity continuity; do not run full pose for non-target dancers. A future pose model may replace RTMPose-m only by returning the same normalized keypoint contract.

- [ ] **Step 4: Implement basic beat extraction**

Extract mono WAV with FFmpeg and use librosa for tempo and beat frames. Strong beats are confidence-ranked accents, not semantic music sections. Missing or low-quality audio returns an empty beat list and never blocks pose analysis.

- [ ] **Step 5: Implement explainable segmentation and package writing**

Generate action boundaries from smoothed pose features, snap within the tested beat tolerance, assign objective difficulty reasons, and group similar non-contiguous segments with `repeatGroupId`. Write into a temporary directory, validate every member, ZIP, hash, then atomically publish.

- [ ] **Step 6: Run synthetic tests and the real target-analysis gate**

Run all worker tests, then analyze the selected dancer in `STAGE_LAB_ACCEPTANCE_VIDEO`. Expected: valid package, non-empty spotlight and pose tracks, non-empty timeline, no NaN/Infinity, and no identity switch hidden as high confidence. Record elapsed time, peak memory, device, and package size.

- [ ] **Step 7: Commit**

```bash
git add backend/workers/analysis
git commit -m "feat: generate dance analysis package"
```

### Task 8: Import And Render Real Analysis In The Practice Player

**Files:**
- Create: `kpop/Domain/Analysis/AnalysisPackage.swift`
- Create: `kpop/Domain/Analysis/TrackInterpolator.swift`
- Create: `kpop/Views/PracticeAnalysisOverlay.swift`
- Create: `kpopTests/AnalysisPackageTests.swift`
- Create: `kpopTests/TrackInterpolatorTests.swift`
- Create: `kpopTests/PracticeOverlayGeometryTests.swift`
- Modify: `kpop/Core/Networking/AnalysisAPIClient.swift`
- Modify: `kpop/Core/Persistence/AnalysisPackageStore.swift`
- Modify: `kpop/Views/RealAnalysisModel.swift`
- Modify: `kpop/Views/PracticePlaceholderView.swift`
- Modify: `kpop/Views/PracticePlayerView.swift`
- Modify: `kpop/Models/DanceProject.swift`

**Interfaces:**
- Produces: decoded immutable `AnalysisPackage` and time-indexed interpolation APIs.
- Produces: authenticated streaming result download with byte-count and SHA-256 validation.
- Produces: aspect-fit/fill aware overlay geometry supporting orientation and mirroring.
- Consumes: Stage 7 package and current AVPlayer time.

- [ ] **Step 1: Write failing package decode and integrity tests**

Test required ZIP members, schema version, inner hashes, outer hash, normalized coordinates, monotonic timestamps, unsupported schema, truncation, path traversal, and atomic replacement that preserves a prior valid package after failure.

- [ ] **Step 2: Write failing interpolation and geometry tests**

Test exact keyframes, linear interpolation, low-confidence suppression, pre/post bounds, mirrored X coordinates, portrait/landscape transforms, letterboxing, and skeleton joint omission below confidence threshold.

- [ ] **Step 3: Implement streamed result import**

Download to an Application Support temporary file rather than loading the ZIP into one `Data` value. Validate byte count and SHA-256, decode and validate manifest members, then atomically replace the project package. Transition remote state from `resultReady` to local importing/completed only after validation.

- [ ] **Step 4: Render spotlight and optional skeleton**

Overlay a soft spotlight around the interpolated target box and dim the non-target area without obscuring controls. Add a persisted per-project skeleton toggle. Low-confidence intervals show a yellow status chip and weak/no spotlight instead of a confident lock.

- [ ] **Step 5: Replace sample timeline only when a real package exists**

Map package segments to the existing node UI with difficulty reasons and repeat badges. Projects without a package keep the current Demo timeline only when explicitly in Preview/Fake mode; production UI shows an honest unavailable state.

- [ ] **Step 6: Run iOS regression and manual simulator smoke**

Run `./scripts/verify-ios.sh`, then launch the iPhone 17 Simulator against local AI and verify result import, seek, speed, mirror, loop, skeleton toggle, low-confidence indication, and offline reopen.

- [ ] **Step 7: Commit**

```bash
git add kpop kpopTests
git commit -m "feat: render real dance analysis"
```

### Task 9: Complete The One-Video End-To-End Acceptance

**Files:**
- Create: `scripts/run-local-ai-demo.sh`
- Create: `docs/development/local-ai-demo.md`
- Create: `docs/ai/MODEL_LICENSES.md`
- Create: `docs/ai/ACCEPTANCE_TEMPLATE.md`
- Modify: `scripts/verify-backend.sh`
- Modify: `scripts/verify-ios.sh`
- Modify: `scripts/verify-local-ai.sh`
- Modify: `backend/README.md`
- Modify: `docs/PROJECT_STATUS.md` for non-blocking issues, measured limitations, and acceptance evidence.

**Interfaces:**
- Produces: one command that starts local AI mode with explicit loopback or paired-LAN configuration and prints no secret after startup setup.
- Produces: a repeatable acceptance record without storing the test video, screenshots, names, paths, or model-generated candidate images in Git.

- [ ] **Step 1: Add complete verification gates**

`verify-local-ai.sh` runs synthetic worker tests and the runtime probe without reading the acceptance video. `verify-backend.sh` runs API contracts with a fake runner. `verify-ios.sh` runs Swift unit/UI tests and Staging/Release builds without requiring the local AI service.

- [ ] **Step 2: Document loopback and real-device pairing**

Document exact simulator startup. For real iPhone, generate a random short-lived pairing token at process startup, bind only to the selected private LAN interface, inject base URL/token through the Debug scheme, reject non-private addresses, and invalidate the token when the process stops. Do not commit Xcode user scheme files containing local values.

- [ ] **Step 3: Run the full automated gate**

Run:

```bash
./scripts/verify-local-ai.sh
./scripts/verify-backend.sh
./scripts/verify-ios.sh
```

Expected: all worker, backend, Swift, UI, Staging, and Release checks pass with zero failures. Record command date, environment, pass/fail counts, and unexecuted checks.

- [ ] **Step 4: Run the one-video product acceptance**

Using `82MAJOR Trophy`, verify real candidate images, choose one dancer, complete target analysis, import the package, and exercise spotlight, skeleton toggle, low-confidence state, timeline seek, difficulty, repeat badges, speed, mirror, loop, and offline reopen. Manually mark at least 10 visible action changes and calculate median absolute nearest-node error; target is at most `0.5` seconds.

- [ ] **Step 5: Perform privacy and resource inspection**

Confirm logs contain no token, absolute path, video title, source filename, frame, or candidate image. Confirm intermediate files live only under the ignored workspace, deletion removes them, no Google Cloud GPU exists, and no cloud resource configuration changed.

- [ ] **Step 6: Update long-term documentation**

Record actual architecture, data flow, storage locations, API endpoints, model versions/licenses, elapsed time, peak memory, package size, limitations, and the difference between local real AI and cloud deployment. Mark Stage 6 `待验收`, not complete.

- [ ] **Step 7: Run review and commit**

Use `superpowers:requesting-code-review`, resolve every P0/P1 finding, rerun all gates, then commit.

```bash
git add scripts backend/README.md docs
git commit -m "docs: verify local real AI demo"
```

## Stage Completion Gate

Stage 6 reaches `待验收` only when all nine tasks are committed, all three verification scripts pass, the real video acceptance record meets the identity/skeleton/timeline criteria, no high-priority review finding remains, no cloud GPU or paid service was enabled, and the project status distinguishes measured results from planned behavior. The user must explicitly accept Stage 6 before any three-video expansion or Google Cloud Worker design begins.
