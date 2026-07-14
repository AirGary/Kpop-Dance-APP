# Stage 3 iOS Local API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect the Debug iOS Simulator build to the local Stage 2 FastAPI jobs API while preserving the existing offline demo flow.

**Architecture:** A concrete `JobsAPIClient` owns the HTTP contract and accepts an injected send closure for deterministic tests. `JobCreationInputFactory` validates local project/video metadata, and a main-actor `AnalysisConnectionModel` coordinates create/fetch/persistence for `AnalysisView`.

**Tech Stack:** Swift 5, SwiftUI, SwiftData, Foundation `URLSession`, Swift Testing, FastAPI on `127.0.0.1`.

## Global Constraints

- Only Debug may use `http://127.0.0.1:8000`; Staging and Release must not contain a localhost API URL.
- Use only `POST /v1/jobs` and `GET /v1/jobs/{job_id}`.
- Use local development token `dev-user-a`; do not treat it as production auth.
- Do not upload video bytes, deploy cloud resources, add SDK dependencies, poll, or replace the fake dancer/result flow.
- Never log authorization, request JSON, video names, fingerprints, absolute paths, or response bodies.
- Persist `remoteJobId` and `sourceFingerprint` only after create and fetch both succeed.
- Every behavior change starts with a failing test.

---

### Task 1: Typed Jobs API Client And Development Configuration

**Files:**
- Create: `kpop/Core/Networking/HTTPTransport.swift`
- Create: `kpop/Core/Networking/JobsAPIClient.swift`
- Create: `kpop/App/JobsAPIConfiguration.swift`
- Create: `kpopTests/JobsAPIClientTests.swift`
- Create: `kpopTests/JobsAPIConfigurationTests.swift`

**Interfaces:**
- Produces: `HTTPTransport.send(URLRequest)`, `JobsAPIConfiguration`, `CreateRemoteJobRequest`, `RemoteJob`, `JobsAPIError`, `JobsAPIClient.createJob(_:idempotencyKey:)`, and `JobsAPIClient.job(id:)`.

- [ ] **Step 1: Write failing configuration and request tests**

Tests construct configuration directly and with an Info dictionary. Assert development accepts `http://127.0.0.1:8000`, non-development returns no client configuration, and invalid URLs are rejected. An injected recording transport asserts:

```swift
#expect(request.httpMethod == "POST")
#expect(request.url?.path == "/v1/jobs")
#expect(request.value(forHTTPHeaderField: "Authorization") == "Bearer dev-user-a")
#expect(request.value(forHTTPHeaderField: "Idempotency-Key") == "project-key")
#expect(try JSONSerialization.jsonObject(with: body) as? [String: Any] == expectedJSON)
```

Response tests cover create `201`, replay `200`, fetch `200`, backend `409` envelope, malformed JSON, and non-HTTP response.

- [ ] **Step 2: Verify RED**

Run:

```bash
xcodebuild -project kpop.xcodeproj -scheme kpop -destination 'platform=iOS Simulator,name=iPhone 17' -only-testing:kpopTests/JobsAPIClientTests -only-testing:kpopTests/JobsAPIConfigurationTests test
```

Expected: compile failure because networking types do not exist.

- [ ] **Step 3: Implement the minimal client**

Use these public shapes:

```swift
nonisolated struct HTTPTransport: Sendable {
    let send: @Sendable (URLRequest) async throws -> (Data, URLResponse)
    static let live = HTTPTransport { try await URLSession.shared.data(for: $0) }
}

nonisolated struct JobsAPIConfiguration: Equatable, Sendable {
    let baseURL: URL
    let bearerToken: String
    static func from(infoDictionary: [String: Any]) throws -> JobsAPIConfiguration?
}

nonisolated struct CreateRemoteJobRequest: Codable, Equatable, Sendable {
    let projectId: UUID
    let sourceFingerprint: String
    let durationSeconds: Double
    let byteCount: Int64
    let mimeType: String
}

nonisolated struct RemoteJob: Codable, Equatable, Sendable {
    let id: UUID
    let projectId: UUID
    let state: AnalysisJobState
    let progress: Double
    let errorCode: String?
    let createdAt: Date
    let updatedAt: Date
}
```

`JobsAPIClient` must build paths with `URL.appending(path:)`, encode camelCase fields exactly, accept `200` or `201` for create, require `200` for fetch, decode the shared error envelope, and map transport/response/decoding failures without printing sensitive values. Use a custom ISO-8601 decoder that accepts timestamps with or without fractional seconds.

- [ ] **Step 4: Verify GREEN and full iOS tests**

Run the focused command from Step 2, then:

```bash
xcodebuild -project kpop.xcodeproj -scheme kpop -destination 'platform=iOS Simulator,name=iPhone 17' test
```

Expected: PASS.

- [ ] **Step 5: Commit**

Commit: `feat: add typed iOS jobs API client`

---

### Task 2: Local Project Metadata Validation

**Files:**
- Create: `kpop/Core/Networking/JobCreationInput.swift`
- Create: `kpopTests/JobCreationInputTests.swift`

**Interfaces:**
- Consumes: `CreateRemoteJobRequest`.
- Produces: `JobCreationInput(request:idempotencyKey:)`, `JobCreationInputError`, and `JobCreationInputFactory.make(project:fileManager:)`.

- [ ] **Step 1: Write failing metadata tests**

Create temporary `.mp4` and `.mov` files and assert exact MIME, byte count, duration, fingerprint `project:<lowercase UUID>`, and idempotency key `project-<lowercase UUID>`. Add separate tests for missing path, missing file, unsupported extension, duration `0` and `360.0001`, zero-byte file, and file larger than 2 GiB through injected file attributes.

- [ ] **Step 2: Verify RED**

Run:

```bash
xcodebuild -project kpop.xcodeproj -scheme kpop -destination 'platform=iOS Simulator,name=iPhone 17' -only-testing:kpopTests/JobCreationInputTests test
```

Expected: compile failure because `JobCreationInputFactory` does not exist.

- [ ] **Step 3: Implement minimal validation**

Use:

```swift
nonisolated struct JobCreationInput: Equatable, Sendable {
    let request: CreateRemoteJobRequest
    let idempotencyKey: String
}

@MainActor
enum JobCreationInputFactory {
    static func make(
        project: DanceProject,
        fileManager: FileManager = .default
    ) throws -> JobCreationInput
}
```

Reject metadata locally before constructing the request. Do not hash or read video bytes; the Stage 3 fingerprint is project-scoped and intentionally temporary.

- [ ] **Step 4: Verify GREEN and suite**

Run the focused test and complete iOS test command. Expected: PASS.

- [ ] **Step 5: Commit**

Commit: `feat: validate local job metadata`

---

### Task 3: Analysis Connection State And Persistence

**Files:**
- Create: `kpop/Views/AnalysisConnectionModel.swift`
- Create: `kpopTests/AnalysisConnectionModelTests.swift`

**Interfaces:**
- Consumes: `JobsAPIClient`, `JobCreationInputFactory`, `DanceProject`.
- Produces: `AnalysisConnectionState` and `AnalysisConnectionModel.connect(project:client:)`.

- [ ] **Step 1: Write failing state tests**

Use a temporary video and injected client transport. Assert idle becomes loading then connected, create is followed by fetch, returned project ID must match, and successful completion writes both `remoteJobId` and `sourceFingerprint`. Assert create failure, fetch failure, and mismatched project ID produce failed state without changing either project field; a second call can retry successfully.

- [ ] **Step 2: Verify RED**

Run:

```bash
xcodebuild -project kpop.xcodeproj -scheme kpop -destination 'platform=iOS Simulator,name=iPhone 17' -only-testing:kpopTests/AnalysisConnectionModelTests test
```

Expected: compile failure because the connection model does not exist.

- [ ] **Step 3: Implement the main-actor model**

Use an observable state enum with `idle`, `loading`, `connected(RemoteJob)`, and `failed(String)`. `connect` must build input, await create, await fetch, validate job/project IDs, then persist project fields and `updatedAt`. Catch known metadata/API errors and expose concise Chinese recovery text without including sensitive values.

- [ ] **Step 4: Verify GREEN and suite**

Run focused and full iOS tests. Expected: PASS.

- [ ] **Step 5: Commit**

Commit: `feat: coordinate remote analysis job`

---

### Task 4: Analysis UI Wiring And Final Local Smoke Test

**Files:**
- Modify: `kpop.xcodeproj/project.pbxproj`
- Modify: `kpop/kpopApp.swift`
- Modify: `kpop/Views/RootView.swift`
- Modify: `kpop/Views/AnalysisPlaceholderView.swift`
- Create: `kpop/App/JobsAPIEnvironment.swift`
- Modify: `backend/README.md`

**Interfaces:**
- Consumes: `JobsAPIConfiguration`, `JobsAPIClient`, `AnalysisConnectionModel`.
- Produces: app-root client injection and the visible local-backend connection card.

- [ ] **Step 1: Write failing environment/UI assertions**

Extend configuration tests to load Debug build values and add a launch-safe UI assertion that the home screen still opens without a backend. Assert source files/build settings contain no localhost URL for Staging or Release.

- [ ] **Step 2: Verify RED**

Run focused configuration tests. Expected: FAIL because the build setting and environment key are absent.

- [ ] **Step 3: Wire development configuration and UI**

Use `#if DEBUG` to build the `http://127.0.0.1:8000` client only in Debug; Staging and Release inject `nil`. Build the optional client once in `kpopApp`, inject it through a custom SwiftUI environment key, and leave previews/tests safe when absent.

Add an analysis card with:

- `创建云分析任务` while idle or failed.
- A disabled progress button while loading.
- Job short ID, `draft`, and `0%` when connected.
- Concise error text plus retry when failed.
- A note that Stage 3 sends metadata only and the existing Demo completion controls remain separate.

Update `backend/README.md` with the two-terminal simulator procedure only; do not add deployment instructions.

- [ ] **Step 4: Run all verification**

Run:

```bash
./scripts/verify-backend.sh
./scripts/verify-ios.sh
git diff --check HEAD
```

Expected: backend 42+ tests pass, all iOS tests pass, Staging and Release build, and no whitespace errors.

- [ ] **Step 5: Perform the local HTTP contract smoke test**

Start Uvicorn on `127.0.0.1:8000`, issue the same create/fetch sequence the client uses, verify `201/200`, and stop the server. If simulator UI automation cannot safely tap an imported-video project, document that manual UI tap remains the only residual check; do not weaken file validation for the test.

- [ ] **Step 6: Commit**

Commit: `feat: connect analysis UI to local backend`

## Completion Gate

- Debug Simulator can create and fetch a real local draft job.
- Existing offline Demo navigation remains usable.
- Staging and Release contain no localhost endpoint.
- No video bytes or cloud requests are sent.
- Backend and iOS verification scripts pass.
- Working tree is clean on `codex/video-practice-mvp`.
