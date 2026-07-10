# Stage 1 Local Domain Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a tested local domain foundation for cloud-analysis jobs, project persistence, managed video files, analysis packages, and deterministic fake analysis services without changing the current user flow.

**Architecture:** Keep `DanceProject` and `ProjectPhase` compatible with the current views. Introduce a separate Codable `AnalysisJobSnapshot` and pure `AnalysisStateMachine`, then put persistence, files, and fake cloud behavior behind small protocols. Stage 1 does not call a network or add cloud SDKs.

**Tech Stack:** Swift 5 language mode, Swift 6.3.3 toolchain, SwiftUI, SwiftData, Foundation, CryptoKit, Swift Testing, Xcode 26.6, iOS 18.0.

## Global Constraints

- Preserve all current Home, Import, Analysis, Dancer Selection, and Practice behavior.
- Do not add Firebase, Google Cloud, CloudKit, StoreKit, HTTP requests, or AI models.
- Do not remove or rename existing persisted `DanceProject` properties.
- All new persistent properties must be optional or have safe defaults for lightweight migration.
- The app and all tests must pass `./scripts/verify-ios.sh` after every task.
- Each task uses a failing test before production behavior is added.

---

### Task 1: Analysis Job Domain and State Machine

**Files:**
- Create: `kpop/Domain/Analysis/AnalysisJobState.swift`
- Create: `kpop/Domain/Analysis/AnalysisJobSnapshot.swift`
- Create: `kpop/Domain/Analysis/AnalysisStateMachine.swift`
- Create: `kpopTests/AnalysisStateMachineTests.swift`

**Interfaces:**
- Produces: `AnalysisJobState`, `AnalysisJobSnapshot`, `AnalysisStateMachine.canTransition(from:to:)`, and `AnalysisStateMachine.transition(_:to:)`.

- [ ] Write tests that verify the approved happy path, confirmation loop, failure/cancellation paths, and rejection of invalid transitions.
- [ ] Run `xcodebuild ... -only-testing:kpopTests/AnalysisStateMachineTests test`; expect missing-type compile failures.
- [ ] Implement the exact states: `draft`, `preparing`, `uploading`, `uploaded`, `detecting`, `awaitingTarget`, `queued`, `analyzing`, `awaitingConfirmation`, `resultReady`, `importing`, `completed`, `failedRecoverable`, `failedTerminal`, `cancelling`, `deleted`.
- [ ] Make `transition` throw `AnalysisStateTransitionError.invalidTransition(from:to:)` when `canTransition` is false.
- [ ] Run the focused tests and full iOS verification.
- [ ] Commit with `feat: add analysis job state machine`.

Approved transition table:

```text
draft -> preparing, cancelling
preparing -> uploading, failedRecoverable, failedTerminal, cancelling
uploading -> uploaded, failedRecoverable, failedTerminal, cancelling
uploaded -> detecting, failedRecoverable, failedTerminal, cancelling
detecting -> awaitingTarget, failedRecoverable, failedTerminal, cancelling
awaitingTarget -> queued, cancelling
queued -> analyzing, failedRecoverable, failedTerminal, cancelling
analyzing -> awaitingConfirmation, resultReady, failedRecoverable, failedTerminal, cancelling
awaitingConfirmation -> analyzing, cancelling
resultReady -> importing, failedRecoverable, cancelling
importing -> completed, failedRecoverable, failedTerminal, cancelling
failedRecoverable -> preparing, uploading, detecting, queued, analyzing, importing, cancelling
cancelling -> deleted
completed -> deleted
failedTerminal -> deleted
deleted -> no transitions
```

`AnalysisJobSnapshot` fields:

```swift
struct AnalysisJobSnapshot: Identifiable, Codable, Equatable, Sendable {
    let id: UUID
    let projectID: UUID
    var state: AnalysisJobState
    var progress: Double
    var errorCode: String?
    var updatedAt: Date
}
```

---

### Task 2: Managed Video and Analysis Package Stores

**Files:**
- Create: `kpop/Core/Persistence/ManagedFilePath.swift`
- Create: `kpop/Core/Persistence/VideoFileStore.swift`
- Create: `kpop/Core/Persistence/AnalysisPackageStore.swift`
- Modify: `kpop/Models/ImportedVideo.swift`
- Create: `kpopTests/ManagedFileStoreTests.swift`

**Interfaces:**
- Produces: managed relative file paths; `VideoFileStore.importVideo(from:)`, `resolve(_:)`, `delete(_:)`; `AnalysisPackageStore.save(_:projectID:version:)`, `load(_:)`, and `delete(_:)`.

- [ ] Write tests using a unique temporary root directory. Verify copy, relative-path resolution, replacement-safe package writes, SHA-256, and deletion.
- [ ] Run focused tests; expect missing-type compile failures.
- [ ] Implement `ManagedFilePath` as a validated relative path that rejects absolute paths and `..` components.
- [ ] Store videos under `ImportedVideos/<UUID>.<extension>`.
- [ ] Store packages under `AnalysisPackages/<projectID>/result-v<version>.bin` using temporary-write then atomic replacement.
- [ ] Return `AnalysisPackageRecord(relativePath:schemaVersion:sha256:byteCount:)` from package saves.
- [ ] Refactor `ImportedVideoStore` to delegate copying to `VideoFileStore` while preserving its existing public method and absolute `ImportedVideo.fileURL` output.
- [ ] Run focused tests and full iOS verification.
- [ ] Commit with `feat: add managed project file stores`.

---

### Task 3: SwiftData Project Repository and Migration-Safe Metadata

**Files:**
- Modify: `kpop/Models/DanceProject.swift`
- Modify: `kpop/App/ModelContainerFactory.swift`
- Create: `kpop/Core/Persistence/DanceProjectRepository.swift`
- Create: `kpop/Core/Persistence/SwiftDataDanceProjectRepository.swift`
- Create: `kpopTests/DanceProjectRepositoryTests.swift`

**Interfaces:**
- Produces: `DanceProjectRepository.fetchAll()`, `fetch(id:)`, `insert(_:)`, `save()`, and `delete(_:)` on `@MainActor`.

- [ ] Write in-memory repository tests for sort order, ID lookup, insert/save, and delete.
- [ ] Run focused tests; expect missing repository-type failures.
- [ ] Add migration-safe `DanceProject` properties with defaults: `sourceFingerprint = ""`, `remoteJobId: String?`, `analysisSchemaVersion: Int?`, `analysisPackageRelativePath: String?`, `lastPracticedAt: Date?`.
- [ ] Implement the repository over an injected `ModelContext`; every mutating operation updates `updatedAt` where appropriate.
- [ ] Keep `ModelContainerFactory` schema explicit and containing `DanceProject.self`.
- [ ] Run focused tests and full iOS verification.
- [ ] Commit with `feat: add project repository foundation`.

---

### Task 4: Analysis Service Protocol and Deterministic Fake

**Files:**
- Create: `kpop/Domain/Analysis/DancerCandidate.swift`
- Create: `kpop/Domain/Analysis/AnalysisResultDescriptor.swift`
- Create: `kpop/Core/Services/AnalysisService.swift`
- Create: `kpop/Core/Services/FakeAnalysisService.swift`
- Create: `kpopTests/FakeAnalysisServiceTests.swift`

**Interfaces:**
- Produces: async `AnalysisService` methods `startDetection(projectID:)`, `candidates(jobID:)`, `selectTarget(jobID:candidateID:)`, `status(jobID:)`, and `result(jobID:)`.

- [ ] Write tests for deterministic job creation, stable candidates, target selection, completion, unknown job errors, and requesting a result before completion.
- [ ] Run focused tests; expect missing protocol/type failures.
- [ ] Implement `FakeAnalysisService` as an actor with an in-memory job dictionary and fixed candidate data.
- [ ] Make fake state transitions use `AnalysisStateMachine`; do not duplicate transition rules.
- [ ] Make `selectTarget` progress through `queued`, `analyzing`, `resultReady`, and `completed` deterministically.
- [ ] Run focused tests and full iOS verification.
- [ ] Commit with `feat: add fake analysis service`.

---

### Task 5: Stage 1 Documentation and Final Gate

**Files:**
- Create: `docs/development/local-domain-foundation.md`

**Interfaces:**
- Consumes: all Stage 1 types.
- Produces: a beginner-readable map of domain, persistence, file, and fake service responsibilities.

- [ ] Document each new folder using the four questions: input, output, storage location, and failure owner.
- [ ] Include one sequence showing `FakeAnalysisService.startDetection -> candidates -> selectTarget -> result`.
- [ ] Run `./scripts/verify-ios.sh`.
- [ ] Run `git status --short`, `git diff --check HEAD`, and confirm only the documentation file remains for this task.
- [ ] Commit with `docs: explain local domain foundation`.

## Completion Gate

- Existing UI and real local video playback still compile and launch.
- All Stage 0 and Stage 1 unit/UI tests pass.
- Invalid analysis-state transitions are rejected.
- All managed files remain inside their injected root directories.
- Repository tests use an in-memory SwiftData container.
- Fake analysis never performs network or disk access.
- Git working tree is clean.

After completion, Stage 2 may add the FastAPI/Firestore/Storage development backend against the stable `AnalysisService` and result contracts.
