# Stage 4 Resumable Local Upload Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a locally runnable, resumable upload path that compresses an imported iOS video to a managed 1080p MP4, uploads ordered chunks to FastAPI, validates SHA-256, and creates one draft analysis job.

**Architecture:** FastAPI owns upload sessions through a service layer with in-memory metadata and an owner-isolated local object store. SwiftUI uses a typed upload client and a resumable coordinator, with migration-safe project metadata and explicit UI states. Existing fake analysis navigation and the Stage 3 jobs diagnostic remain intact.

**Tech Stack:** Python 3.13, FastAPI, Pydantic 2, pytest, Swift 5, SwiftUI, SwiftData, AVFoundation, CryptoKit, XCTest/Swift Testing.

## Global Constraints

- No Google Cloud resources, SDK calls, or deployment are introduced.
- Upload only `video/mp4`, duration in `(0, 360]`, bytes in `(0, 2147483648]`, and a 64-character lowercase SHA-256.
- Chunk size is exactly `5_242_880` bytes and sessions expire after 24 hours.
- Upload tokens are random, stored only as SHA-256 digests, and never logged.
- Default iOS networking rejects expensive cellular access; one confirmed upload may enable it without persisting that choice.
- The original imported video is never modified or removed by the upload flow.
- Existing Stage 2 and Stage 3 behavior must remain passing.

## File Map

- `backend/api/app/schemas/uploads.py`: upload request/response contracts and range types.
- `backend/api/app/ports/upload_repository.py`: upload session persistence protocol and entity.
- `backend/api/app/adapters/repositories/in_memory_upload_repository.py`: lock-protected development repository.
- `backend/api/app/ports/upload_object_store.py`: bounded file-operation protocol.
- `backend/api/app/adapters/storage/local_upload_object_store.py`: safe append, compare, hash, size, and delete operations.
- `backend/api/app/services/upload_service.py`: session, token, range, expiry, idempotency, completion, and Job creation rules.
- `backend/api/app/routes/uploads.py`: authenticated control-plane endpoints and token-authenticated content endpoints.
- `kpop/Core/Networking/UploadAPIClient.swift`: exact create, HEAD, chunk PUT, and complete HTTP contracts.
- `kpop/Core/Services/VideoCompressionService.swift`: managed 1080p MP4 export.
- `kpop/Core/Services/ResumableUploadCoordinator.swift`: hash, resume, chunk loop, progress, completion, and cleanup orchestration.
- `kpop/Models/DanceProject.swift`: optional resumable-upload metadata.
- `kpop/Views/UploadConnectionModel.swift`: UI-safe state machine around the coordinator.
- `kpop/Views/AnalysisPlaceholderView.swift`: upload card while retaining current diagnostic and fake flow.

---

### Task 1: Upload Session Domain And Repository

**Files:**
- Create: `backend/api/app/schemas/uploads.py`
- Create: `backend/api/app/ports/upload_repository.py`
- Create: `backend/api/app/adapters/repositories/in_memory_upload_repository.py`
- Test: `backend/tests/unit/test_upload_repository.py`

**Interfaces:**
- Produces: `CreateUploadRequest`, `UploadSessionResponse`, `UploadSession`, and `UploadRepository`.
- Produces: async repository methods `create`, `get`, `find_idempotent`, `update_offset`, `mark_completed`, `delete`, and `expired_before`.

- [ ] **Step 1: Write failing schema and repository tests**

```python
def test_create_upload_rejects_non_lowercase_sha256():
    with pytest.raises(ValidationError):
        CreateUploadRequest(
            projectId=uuid4(), sourceFingerprint="source", durationSeconds=90,
            byteCount=10, mimeType="video/mp4", sha256="A" * 64,
        )

@pytest.mark.anyio
async def test_repository_updates_only_expected_offset():
    repository = InMemoryUploadRepository()
    session = make_upload_session(offset=0)
    await repository.create(session)
    assert await repository.update_offset(session.id, expected=0, new=5) is True
    assert await repository.update_offset(session.id, expected=0, new=10) is False
```

- [ ] **Step 2: Run tests and confirm RED**

Run: `cd backend && .venv/bin/pytest tests/unit/test_upload_repository.py -q`

Expected: collection fails because upload modules do not exist.

- [ ] **Step 3: Implement validated contracts and lock-protected repository**

```python
class CreateUploadRequest(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    project_id: UUID
    source_fingerprint: str = Field(min_length=1, max_length=256)
    duration_seconds: float = Field(gt=0, le=360)
    byte_count: int = Field(gt=0, le=2_147_483_648)
    mime_type: Literal["video/mp4"]
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

@dataclass(frozen=True, slots=True)
class UploadSession:
    id: UUID
    owner_id: str
    request: CreateUploadRequest
    request_digest: str
    idempotency_key: str
    token_digest: str
    offset: int
    expires_at: datetime
    completed_job_id: UUID | None = None
```

Use one `asyncio.Lock` around compare-and-set and idempotency indexes so two requests cannot advance the same offset.

- [ ] **Step 4: Run focused and backend regression tests**

Run: `cd backend && .venv/bin/pytest tests/unit/test_upload_repository.py tests/unit/test_job_service.py -q`

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/api/app/schemas/uploads.py backend/api/app/ports/upload_repository.py backend/api/app/adapters/repositories/in_memory_upload_repository.py backend/tests/unit/test_upload_repository.py
git commit -m "feat: add upload session domain"
```

### Task 2: Owner-Isolated Local Upload Object Store

**Files:**
- Create: `backend/api/app/ports/upload_object_store.py`
- Create: `backend/api/app/adapters/storage/local_upload_object_store.py`
- Test: `backend/tests/unit/test_local_upload_object_store.py`

**Interfaces:**
- Consumes: owner ID and upload UUID from Task 1.
- Produces: `LocalUploadObjectStore.size`, `append`, `matches`, `sha256`, and `delete` async methods.

- [ ] **Step 1: Write failing traversal, append, replay, hash, and delete tests**

```python
@pytest.mark.anyio
async def test_append_and_compare_do_not_require_whole_file(tmp_path):
    store = LocalUploadObjectStore(tmp_path)
    upload_id = uuid4()
    await store.append("owner-a", upload_id, 0, chunks(b"abc", b"def"))
    assert await store.size("owner-a", upload_id) == 6
    assert await store.matches("owner-a", upload_id, 3, chunks(b"def")) is True
    assert await store.sha256("owner-a", upload_id) == hashlib.sha256(b"abcdef").hexdigest()
    await store.delete("owner-a", upload_id)
    assert await store.size("owner-a", upload_id) == 0

@pytest.mark.anyio
async def test_owner_component_rejects_traversal(tmp_path):
    with pytest.raises(UnsafeUploadPathError):
        await LocalUploadObjectStore(tmp_path).size("../foreign", uuid4())
```

- [ ] **Step 2: Run tests and confirm RED**

Run: `cd backend && .venv/bin/pytest tests/unit/test_local_upload_object_store.py -q`

Expected: collection fails because the object store is absent.

- [ ] **Step 3: Implement bounded streaming file operations**

```python
class UploadObjectStore(Protocol):
    async def size(self, owner_id: str, upload_id: UUID) -> int: ...
    async def append(self, owner_id: str, upload_id: UUID, offset: int,
                     chunks: AsyncIterator[bytes]) -> int: ...
    async def matches(self, owner_id: str, upload_id: UUID, offset: int,
                      chunks: AsyncIterator[bytes]) -> bool: ...
    async def sha256(self, owner_id: str, upload_id: UUID) -> str: ...
    async def delete(self, owner_id: str, upload_id: UUID) -> None: ...
```

Resolve every object below `<root>/<owner>/uploads/<uuid>/source.mp4`, reject path separators in `owner_id`, process at most each yielded buffer in memory, and use `asyncio.to_thread` for blocking file work.

- [ ] **Step 4: Run tests and confirm GREEN**

Run: `cd backend && .venv/bin/pytest tests/unit/test_local_upload_object_store.py -q`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/api/app/ports/upload_object_store.py backend/api/app/adapters/storage/local_upload_object_store.py backend/tests/unit/test_local_upload_object_store.py
git commit -m "feat: add local resumable object store"
```

### Task 3: Upload Service Rules And Job Completion

**Files:**
- Create: `backend/api/app/services/upload_service.py`
- Modify: `backend/api/app/container.py`
- Modify: `backend/api/app/main.py`
- Test: `backend/tests/unit/test_upload_service.py`
- Test: `backend/tests/api/test_upload_cleanup.py`

**Interfaces:**
- Consumes: `UploadRepository`, `UploadObjectStore`, `JobService`, and `Callable[[], datetime]`.
- Produces: `create_session`, `head`, `append_chunk`, `complete`, and `cleanup_expired` methods plus typed service errors.

- [ ] **Step 1: Write failing service tests for idempotency, token secrecy, ordered ranges, replay, expiry, checksum, and completion**

```python
@pytest.mark.anyio
async def test_complete_creates_exactly_one_job(upload_service, upload_request):
    created = await upload_service.create_session("owner-a", "create-key", upload_request)
    await upload_service.append_chunk(
        created.upload_id, created.token, start=0, end=2, total=3, chunks=chunks(b"abc")
    )
    first = await upload_service.complete("owner-a", created.upload_id, "complete-key")
    second = await upload_service.complete("owner-a", created.upload_id, "complete-key")
    assert first.job.id == second.job.id
    assert first.created is True
    assert second.created is False

@pytest.mark.anyio
async def test_checksum_mismatch_deletes_bytes(upload_service, object_store):
    created = await upload_service.create_session("owner-a", "key", request_for(b"abc", sha="0" * 64))
    await upload_service.append_chunk(created.upload_id, created.token, 0, 2, 3, chunks(b"abc"))
    with pytest.raises(ChecksumMismatchError):
        await upload_service.complete("owner-a", created.upload_id, "complete")
    assert await object_store.size("owner-a", created.upload_id) == 0
```

- [ ] **Step 2: Run tests and confirm RED**

Run: `cd backend && .venv/bin/pytest tests/unit/test_upload_service.py -q`

Expected: collection fails because `UploadService` is absent.

- [ ] **Step 3: Implement minimal service logic**

```python
class UploadService:
    CHUNK_SIZE = 5_242_880
    LIFETIME = timedelta(hours=24)

    async def append_chunk(self, upload_id: UUID, token: str, start: int,
                           end: int, total: int,
                           chunks: AsyncIterator[bytes]) -> ChunkResult:
        session = await self._valid_token_session(upload_id, token)
        self._validate_range(session, start, end, total)
        if start == session.offset:
            new_offset = await self._objects.append(session.owner_id, upload_id, start, chunks)
            await self._repository.update_offset(upload_id, start, new_offset)
            return ChunkResult(offset=new_offset, complete=new_offset == total)
        if end + 1 == session.offset and await self._objects.matches(
            session.owner_id, upload_id, start, chunks
        ):
            return ChunkResult(offset=session.offset, complete=session.offset == total)
        raise UploadOffsetConflictError(session.offset)
```

Generate tokens with `secrets.token_urlsafe(32)`, compare digests with `hmac.compare_digest`, hash canonical request JSON for replay checks, reconcile stored offset with actual file size before append, and call `JobService.create_job` only after size and digest validation. Cleanup expired records and objects before operations.

Add a FastAPI lifespan hook that calls `container.upload_service.cleanup_expired()` once at startup; verify an expired repository record and its object are removed when `TestClient` enters its context.

- [ ] **Step 4: Run focused service tests and regressions**

Run: `cd backend && .venv/bin/pytest tests/unit/test_upload_service.py tests/api/test_upload_cleanup.py tests/unit/test_job_service.py tests/unit/test_job_deletion.py -q`

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/api/app/services/upload_service.py backend/api/app/container.py backend/api/app/main.py backend/tests/unit/test_upload_service.py backend/tests/api/test_upload_cleanup.py
git commit -m "feat: implement resumable upload service"
```

### Task 4: FastAPI Upload Contract And Privacy

**Files:**
- Create: `backend/api/app/routes/uploads.py`
- Modify: `backend/api/app/main.py`
- Modify: `backend/tests/contracts/test_openapi.py`
- Modify: `backend/tests/api/test_privacy_logging.py`
- Create: `backend/tests/api/test_uploads.py`
- Create: `backend/contracts/fixtures/upload-session.json`
- Modify: `backend/tests/contracts/test_contracts.py`

**Interfaces:**
- Consumes: `UploadService` from Task 3 and existing bearer dependency/error envelope.
- Produces: `POST /v1/uploads`, `HEAD /v1/uploads/{id}/content`, `PUT /v1/uploads/{id}/content`, and `POST /v1/uploads/{id}/complete`.

- [ ] **Step 1: Write failing API contract tests**

```python
def test_upload_resume_and_complete(client, auth_headers):
    body = upload_body(b"abcdef")
    created = client.post("/v1/uploads", json=body, headers={**auth_headers, "Idempotency-Key": "create"})
    assert created.status_code == 201
    upload_url = created.json()["uploadUrl"]
    first = client.put(upload_url, content=b"abc", headers={"Content-Range": "bytes 0-2/6"})
    assert first.status_code == 308
    assert first.headers["Upload-Offset"] == "3"
    assert client.head(upload_url).headers["Upload-Offset"] == "3"
    final = client.put(upload_url, content=b"def", headers={"Content-Range": "bytes 3-5/6"})
    assert final.status_code == 201
    completed = client.post(
        f'/v1/uploads/{created.json()["uploadId"]}/complete',
        headers={**auth_headers, "Idempotency-Key": "complete"},
    )
    assert completed.status_code == 201
    assert completed.json()["status"] == "draft"
```

Also assert that invalid/expired tokens return the same `404 upload_not_found`, foreign completion is hidden, request logs contain neither token nor query string, and OpenAPI contains exactly the original operations plus these four.

- [ ] **Step 2: Run tests and confirm RED**

Run: `cd backend && .venv/bin/pytest tests/api/test_uploads.py tests/contracts/test_openapi.py -q`

Expected: upload routes return 404 and OpenAPI expectation fails.

- [ ] **Step 3: Add thin routes and exact status/header mapping**

```python
@router.put("/{upload_id}/content", include_in_schema=True)
async def put_content(upload_id: UUID, request: Request, token: str = Query(...)) -> Response:
    byte_range = parse_content_range(request.headers.get("Content-Range"))
    result = await request.app.state.container.upload_service.append_chunk(
        upload_id, token, byte_range.start, byte_range.end,
        byte_range.total, request.stream(),
    )
    return Response(
        status_code=201 if result.complete else 308,
        headers={"Upload-Offset": str(result.offset)},
    )
```

Map validation to the shared safe error envelope and never include the signed URL or token in application logs.

- [ ] **Step 4: Run the complete backend suite**

Run: `./scripts/verify-backend.sh`

Expected: all backend tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/api/app/routes/uploads.py backend/api/app/main.py backend/tests/api/test_uploads.py backend/tests/api/test_privacy_logging.py backend/tests/contracts/test_openapi.py backend/tests/contracts/test_contracts.py backend/contracts/fixtures/upload-session.json
git commit -m "feat: expose resumable upload API"
```

### Task 5: Typed iOS Upload Client And Network Policy

**Files:**
- Create: `kpop/Core/Networking/UploadAPIClient.swift`
- Create: `kpop/Core/Networking/UploadNetworkPolicy.swift`
- Modify: `kpop/Core/Networking/HTTPTransport.swift`
- Test: `kpopTests/UploadAPIClientTests.swift`
- Test: `kpopTests/UploadNetworkPolicyTests.swift`

**Interfaces:**
- Produces: `UploadCreateInput`, `UploadSession`, `UploadChunkResult`, and `UploadAPIClient` methods `create`, `offset`, `putChunk`, and `complete`.
- Produces: `UploadNetworkPolicy.makeSession(allowsCellular:)` with `allowsExpensiveNetworkAccess` matching the argument.

- [ ] **Step 1: Write failing exact-request tests**

```swift
@Test func createUsesBearerAndIdempotencyKey() async throws {
    let recorder = RequestRecorder(response: uploadSessionJSON, status: 201)
    let client = UploadAPIClient(configuration: configuration(), transport: recorder.transport)
    _ = try await client.create(input: .fixture, idempotencyKey: "create-key")
    #expect(recorder.request?.httpMethod == "POST")
    #expect(recorder.request?.url?.path == "/v1/uploads")
    #expect(recorder.request?.value(forHTTPHeaderField: "Authorization") == "Bearer development-token")
    #expect(recorder.request?.value(forHTTPHeaderField: "Idempotency-Key") == "create-key")
}

@Test func defaultSessionRejectsExpensiveNetworks() {
    #expect(UploadNetworkPolicy.configuration(allowsCellular: false).allowsExpensiveNetworkAccess == false)
    #expect(UploadNetworkPolicy.configuration(allowsCellular: true).allowsExpensiveNetworkAccess == true)
}
```

Cover HEAD headers, exact `Content-Range`, 308 acceptance, signed URL used verbatim, complete auth, and shared safe API errors.

- [ ] **Step 2: Run iOS tests and confirm RED**

Run: `./scripts/verify-ios.sh --only-testing kpopTests/UploadAPIClientTests --only-testing kpopTests/UploadNetworkPolicyTests`

Expected: compile fails because upload client types do not exist.

- [ ] **Step 3: Implement the client and per-upload URLSession policy**

```swift
nonisolated struct UploadAPIClient: Sendable {
    func putChunk(url: URL, data: Data, start: Int64, total: Int64) async throws -> UploadChunkResult {
        var request = URLRequest(url: url)
        request.httpMethod = "PUT"
        request.httpBody = data
        let end = start + Int64(data.count) - 1
        request.setValue("bytes \(start)-\(end)/\(total)", forHTTPHeaderField: "Content-Range")
        let (_, response) = try await transport.data(for: request)
        return try decodeChunkResponse(response)
    }
}
```

Never print or interpolate signed upload URLs into logs or user-visible errors.

- [ ] **Step 4: Run focused tests and existing jobs client tests**

Run: `./scripts/verify-ios.sh --only-testing kpopTests/UploadAPIClientTests --only-testing kpopTests/UploadNetworkPolicyTests --only-testing kpopTests/JobsAPIClientTests`

Expected: selected tests pass.

- [ ] **Step 5: Commit**

```bash
git add kpop/Core/Networking/UploadAPIClient.swift kpop/Core/Networking/UploadNetworkPolicy.swift kpop/Core/Networking/HTTPTransport.swift kpopTests/UploadAPIClientTests.swift kpopTests/UploadNetworkPolicyTests.swift
git commit -m "feat: add iOS resumable upload client"
```

### Task 6: Compression, Hashing, And Resumable Coordinator

**Files:**
- Create: `kpop/Core/Services/VideoCompressionService.swift`
- Create: `kpop/Core/Services/UploadStagingStore.swift`
- Create: `kpop/Core/Services/ResumableUploadCoordinator.swift`
- Test: `kpopTests/VideoCompressionServiceTests.swift`
- Test: `kpopTests/UploadStagingStoreTests.swift`
- Test: `kpopTests/ResumableUploadCoordinatorTests.swift`

**Interfaces:**
- Consumes: `UploadAPIClient` from Task 5 and an imported local video URL.
- Produces: `UploadProgress` states and `run(project:sourceURL:allowsCellular:onProgress:) async throws -> UploadCompletion`.

- [ ] **Step 1: Write failing staging and coordinator tests with injected fakes**

```swift
@Test func coordinatorResumesAtServerOffsetAndRemovesStagingAfterSuccess() async throws {
    let api = FakeUploadAPI(offset: 3, completedJobID: jobID)
    let staging = FakeStagingStore(bytes: Data("abcdef".utf8))
    let coordinator = ResumableUploadCoordinator(api: api.client, compressor: .fake, staging: staging.store)
    let result = try await coordinator.run(
        project: .fixture(remoteUploadID: uploadID, confirmedUploadOffset: 0),
        sourceURL: sourceURL, allowsCellular: false, onProgress: { _ in }
    )
    #expect(api.uploadedRanges == [3..<6])
    #expect(result.jobID == jobID)
    #expect(staging.didDelete)
}
```

Also test managed path `Application Support/UploadStaging/<project-id>.mp4`, SHA-256 streaming, 5 MiB chunk boundaries, server offset winning over stale local offset, retry preserving staging, and progress based on confirmed bytes.

- [ ] **Step 2: Run tests and confirm RED**

Run: `./scripts/verify-ios.sh --only-testing kpopTests/VideoCompressionServiceTests --only-testing kpopTests/UploadStagingStoreTests --only-testing kpopTests/ResumableUploadCoordinatorTests`

Expected: compile fails because services do not exist.

- [ ] **Step 3: Implement injectable services and coordinator**

```swift
enum UploadProgress: Sendable, Equatable {
    case compressing
    case hashing
    case uploading(confirmedBytes: Int64, totalBytes: Int64)
    case validating
}

struct UploadCompletion: Sendable, Equatable {
    let uploadID: UUID
    let jobID: UUID
}
```

Use `AVAssetExportSession(asset:presetName: AVAssetExportPreset1920x1080)`, output `.mp4`, `FileHandle.read(upToCount:)` for hashing/chunks, HEAD before every resumed chunk loop, and delete only the managed staging file after successful completion.

- [ ] **Step 4: Run focused tests**

Run: `./scripts/verify-ios.sh --only-testing kpopTests/VideoCompressionServiceTests --only-testing kpopTests/UploadStagingStoreTests --only-testing kpopTests/ResumableUploadCoordinatorTests`

Expected: selected tests pass.

- [ ] **Step 5: Commit**

```bash
git add kpop/Core/Services/VideoCompressionService.swift kpop/Core/Services/UploadStagingStore.swift kpop/Core/Services/ResumableUploadCoordinator.swift kpopTests/VideoCompressionServiceTests.swift kpopTests/UploadStagingStoreTests.swift kpopTests/ResumableUploadCoordinatorTests.swift
git commit -m "feat: coordinate compressed video uploads"
```

### Task 7: Project Persistence, Analysis UI, And End-To-End Verification

**Files:**
- Modify: `kpop/Models/DanceProject.swift`
- Modify: `kpop/kpopApp.swift`
- Create: `kpop/App/UploadAPIEnvironment.swift`
- Create: `kpop/Views/UploadConnectionModel.swift`
- Modify: `kpop/Views/AnalysisPlaceholderView.swift`
- Modify: `kpopTests/ProjectModelTests.swift`
- Create: `kpopTests/UploadConnectionModelTests.swift`
- Create: `backend/tests/smoke/test_resumable_upload_smoke.py`
- Modify: `backend/README.md`

**Interfaces:**
- Consumes: coordinator and completion from Task 6.
- Produces: migration-safe optional project fields `remoteUploadID`, `confirmedUploadOffset`, `uploadExpiresAt`; visible upload state and retry action.

- [ ] **Step 1: Write failing migration and UI-model tests**

```swift
@Test func successfulUploadPersistsJobAndClearsResumeMetadata() async {
    let project = DanceProject.fixture()
    let model = UploadConnectionModel(coordinator: .successful(jobID: jobID))
    await model.start(project: project, sourceURL: sourceURL, allowsCellular: false)
    #expect(project.remoteJobID == jobID.uuidString)
    #expect(project.remoteUploadID == nil)
    #expect(project.confirmedUploadOffset == nil)
    #expect(project.uploadExpiresAt == nil)
    #expect(model.state == .completed(jobID: jobID))
}
```

Cover recoverable failure preserving metadata, upload percentage, validating state, unavailable backend state, and default nil values for old projects.

- [ ] **Step 2: Run tests and confirm RED**

Run: `./scripts/verify-ios.sh --only-testing kpopTests/ProjectModelTests --only-testing kpopTests/UploadConnectionModelTests`

Expected: compile fails because fields and model do not exist.

- [ ] **Step 3: Implement Debug injection and the upload card**

```swift
enum UploadViewState: Equatable {
    case ready, compressing, hashing, uploading(Double), validating
    case completed(jobID: UUID)
    case failed(message: String)
}
```

Inject `UploadAPIClient` only under `#if DEBUG`, show `压缩并上传视频`, one-time cellular confirmation, byte progress, validation, completion, and `继续上传`. Keep `AnalysisConnectionModel` diagnostic and existing fake dancer/result navigation unchanged.

- [ ] **Step 4: Add and run real local smoke test**

The smoke test creates deterministic MP4-like bytes, creates a session, uploads two ranges with a HEAD check between them, completes, and fetches the returned job using the development bearer identity.

Run: `cd backend && .venv/bin/pytest tests/smoke/test_resumable_upload_smoke.py -q`

Expected: one smoke test passes without external network access.

- [ ] **Step 5: Run complete verification and inspect production binaries**

Run: `./scripts/verify-backend.sh`

Run: `./scripts/verify-ios.sh`

Run: `rg -a "127\.0\.0\.1:8000|localhost" build/Staging build/Release || true`

Expected: backend and iOS suites pass; Debug can use the local endpoint; Staging and Release report no local endpoint matches.

- [ ] **Step 6: Verify Codex low-level log suppression remains active**

Run: `sqlite3 ~/.codex/logs_2.sqlite "SELECT name FROM sqlite_master WHERE type='trigger' AND name='block_low_level_logs_insert'; SELECT MAX(id), COUNT(*) FROM logs WHERE UPPER(level) IN ('TRACE','DEBUG','INFO'); PRAGMA wal_checkpoint(PASSIVE);"`

Expected: trigger count is one; after a short interval low-level `MAX(id)` and count do not increase; WAL checkpoint completes without low-level inserts.

- [ ] **Step 7: Commit**

```bash
git add kpop/Models/DanceProject.swift kpop/kpopApp.swift kpop/App/UploadAPIEnvironment.swift kpop/Views/UploadConnectionModel.swift kpop/Views/AnalysisPlaceholderView.swift kpopTests/ProjectModelTests.swift kpopTests/UploadConnectionModelTests.swift backend/tests/smoke/test_resumable_upload_smoke.py backend/README.md
git commit -m "feat: connect resumable upload UI"
```

## Final Acceptance

- [ ] A Debug simulator run can compress, interrupt, resume, validate, and obtain a draft Job from local FastAPI.
- [ ] Retry does not recompress when a valid managed staging file and upload session remain.
- [ ] Invalid checksum bytes are deleted; completed valid bytes remain under the 24-hour policy.
- [ ] No bearer token, upload token, signed URL, hash, fingerprint, video name, or absolute path appears in logs.
- [ ] Existing fake analysis navigation remains usable.
- [ ] Backend, iOS, Staging, and Release verification all pass without cloud deployment.
