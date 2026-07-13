# Stage 2 Local Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a locally runnable FastAPI backend with development authentication, owner-isolated idempotent jobs, safe local object cleanup, stable contracts, and undeployed Google Cloud dev Terraform.

**Architecture:** HTTP routes depend on a `JobService`; the service depends only on `AuthVerifier`, `JobRepository`, and `ObjectStore` ports. Tests use development/in-memory/local adapters, so Stage 2 never contacts Google Cloud and later adapters can replace them without changing routes.

**Tech Stack:** Python 3.13 locally with `requires-python >=3.11`, FastAPI, Pydantic 2, uvicorn, pytest, HTTPX, standard-library asyncio/logging/pathlib, Terraform HCL.

## Global Constraints

- Do not add Firebase, Google Cloud SDKs, Docker, gcloud, AI models, upload endpoints, or iOS networking.
- Do not create or deploy cloud resources; Stage 2 cloud cost must remain USD 0.
- Implement only `GET /healthz`, `GET /v1/me`, `POST /v1/jobs`, `GET /v1/jobs/{job_id}`, and `DELETE /v1/jobs/{job_id}`.
- Never log Authorization, request bodies, source fingerprints, video names, absolute paths, or signed URLs.
- Unknown and foreign-owner jobs both return `404 job_not_found`.
- Maximum duration is exactly 360 seconds; maximum byte count is exactly 2 GiB.
- Every production behavior is preceded by a failing test.
- Run the focused backend test and full backend suite after every task; run iOS verification at the final gate.

---

### Task 1: Backend Package, Health, Request IDs, and Error Envelope

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/api/__init__.py`
- Create: `backend/api/app/__init__.py`
- Create: `backend/api/app/config.py`
- Create: `backend/api/app/main.py`
- Create: `backend/api/app/middleware/request_context.py`
- Create: `backend/api/app/routes/health.py`
- Create: `backend/api/app/schemas/errors.py`
- Create: `backend/tests/api/test_health.py`
- Create: `backend/tests/api/test_errors.py`

**Interfaces:**
- Produces: `create_app(settings: Settings | None = None) -> FastAPI`, `Settings(environment="development")`, request ID middleware, `APIError` and the error response envelope.

- [ ] **Step 1: Write failing API tests**

```python
def test_health_is_public(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "environment": "development"}
    assert response.headers["X-Request-ID"]

def test_unknown_route_uses_error_envelope(client):
    response = client.get("/missing", headers={"X-Request-ID": "request-test"})
    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "not_found",
            "message": "Resource was not found.",
            "requestId": "request-test",
        }
    }
```

- [ ] **Step 2: Verify RED**

Run: `cd backend && python3 -m pytest tests/api/test_health.py tests/api/test_errors.py -q`

Expected: FAIL because the backend package and `create_app` do not exist.

- [ ] **Step 3: Add the package and minimal app**

`pyproject.toml` must declare editable package discovery for `api*`, dependencies `fastapi>=0.115,<1`, `pydantic>=2.10,<3`, `uvicorn>=0.34,<1`, and dev dependencies `httpx>=0.28,<1`, `pytest>=8,<10`, `pytest-asyncio>=0.25,<2`.

Implement a middleware that accepts only visible ASCII request IDs of 1–128 characters; otherwise generate `uuid4().hex`. Store it on `request.state.request_id` and return it as `X-Request-ID`. Register handlers for `APIError`, validation errors, Starlette 404, and uncaught errors.

- [ ] **Step 4: Verify GREEN**

Run: `cd backend && python3 -m pytest tests/api/test_health.py tests/api/test_errors.py -q`

Expected: PASS.

- [ ] **Step 5: Run backend suite and commit**

Run: `cd backend && python3 -m pytest -q`

Commit: `feat: scaffold local FastAPI backend`

---

### Task 2: Development Authentication and Privacy-Safe Request Logging

**Files:**
- Create: `backend/api/app/ports/auth.py`
- Create: `backend/api/app/adapters/auth/development_auth.py`
- Create: `backend/api/app/routes/identity.py`
- Create: `backend/api/app/schemas/identity.py`
- Create: `backend/api/app/container.py`
- Modify: `backend/api/app/main.py`
- Modify: `backend/api/app/middleware/request_context.py`
- Create: `backend/tests/api/test_identity.py`
- Create: `backend/tests/api/test_privacy_logging.py`

**Interfaces:**
- Produces: `AuthenticatedUser(user_id: str)`, async `AuthVerifier.verify(token: str)`, `DevelopmentAuthVerifier`, `GET /v1/me`, and `AppContainer`.

- [ ] **Step 1: Write failing auth and logging tests**

```python
def test_me_returns_development_identity(client):
    response = client.get("/v1/me", headers={"Authorization": "Bearer dev-user-a"})
    assert response.status_code == 200
    assert response.json() == {"userId": "dev-user-a"}

def test_me_rejects_missing_token(client):
    response = client.get("/v1/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"

def test_logs_do_not_contain_token_or_request_body(client, caplog):
    secret = "dev-private-token"
    client.get("/v1/me", headers={"Authorization": f"Bearer {secret}"})
    assert secret not in caplog.text
```

- [ ] **Step 2: Verify RED**

Run: `cd backend && python3 -m pytest tests/api/test_identity.py tests/api/test_privacy_logging.py -q`

Expected: FAIL because `/v1/me` and auth ports do not exist.

- [ ] **Step 3: Implement auth through a port**

`DevelopmentAuthVerifier` accepts `dev-` followed by 1–64 ASCII letters, digits, `_`, or `-`; its complete token becomes the test user ID. A FastAPI dependency extracts exactly one Bearer token and maps every missing/invalid case to `401 unauthorized`.

Request logging emits method, route template when available, status, duration, request ID, and stable error code only. It must never interpolate headers, raw URL IDs, or bodies.

- [ ] **Step 4: Verify GREEN and suite**

Run: `cd backend && python3 -m pytest tests/api/test_identity.py tests/api/test_privacy_logging.py -q`

Run: `cd backend && python3 -m pytest -q`

Expected: PASS.

- [ ] **Step 5: Commit**

Commit: `feat: add development API authentication`

---

### Task 3: Job Models, Validation, Repository, and Idempotency

**Files:**
- Create: `backend/api/app/schemas/jobs.py`
- Create: `backend/api/app/ports/job_repository.py`
- Create: `backend/api/app/adapters/repositories/in_memory_job_repository.py`
- Create: `backend/api/app/services/job_service.py`
- Create: `backend/tests/unit/test_job_validation.py`
- Create: `backend/tests/unit/test_job_service.py`

**Interfaces:**
- Produces: `CreateJobRequest`, `JobResponse`, internal `JobRecord`, async `JobRepository`, `InMemoryJobRepository`, and `JobService.create_job/get_job`.

- [ ] **Step 1: Write failing validation and idempotency tests**

```python
@pytest.mark.parametrize("duration", [0, 360.0001])
def test_duration_outside_supported_range_is_rejected(duration):
    with pytest.raises(ValidationError):
        CreateJobRequest(**valid_request(durationSeconds=duration))

@pytest.mark.asyncio
async def test_same_owner_and_key_returns_original_job(service):
    first, first_created = await service.create_job("dev-user-a", "key-1", request())
    second, second_created = await service.create_job("dev-user-a", "key-1", request())
    assert first.id == second.id
    assert first_created is True
    assert second_created is False

@pytest.mark.asyncio
async def test_same_key_with_changed_body_conflicts(service):
    await service.create_job("dev-user-a", "key-1", request())
    with pytest.raises(APIError) as error:
        await service.create_job("dev-user-a", "key-1", request(durationSeconds=120))
    assert error.value.code == "idempotency_conflict"
```

- [ ] **Step 2: Verify RED**

Run: `cd backend && python3 -m pytest tests/unit/test_job_validation.py tests/unit/test_job_service.py -q`

Expected: FAIL because job types do not exist.

- [ ] **Step 3: Implement models and repository**

Use Pydantic aliases matching JSON camelCase. Validate duration `(0, 360]`, byte count `(0, 2147483648]`, MIME allowlist, and fingerprint regex `^[A-Za-z0-9:_-]{8,128}$`. Use aware UTC datetimes and serialize them as RFC 3339.

The repository stores jobs by UUID and idempotency records by `(owner_id, key)`, protected by `asyncio.Lock`. Compare a canonical SHA-256 hash of the validated request JSON to detect changed-body conflicts. Foreign-owner and unknown IDs both raise `job_not_found`.

- [ ] **Step 4: Verify GREEN and suite**

Run: `cd backend && python3 -m pytest tests/unit/test_job_validation.py tests/unit/test_job_service.py -q`

Run: `cd backend && python3 -m pytest -q`

Expected: PASS.

- [ ] **Step 5: Commit**

Commit: `feat: add idempotent local job service`

---

### Task 4: Safe Local Object Store and Delete Consistency

**Files:**
- Create: `backend/api/app/ports/object_store.py`
- Create: `backend/api/app/adapters/storage/local_object_store.py`
- Modify: `backend/api/app/services/job_service.py`
- Modify: `backend/api/app/container.py`
- Create: `backend/tests/unit/test_local_object_store.py`
- Create: `backend/tests/unit/test_job_deletion.py`

**Interfaces:**
- Produces: async `ObjectStore.delete_job_objects(owner_id, job_id)`, `LocalObjectStore(root: Path)`, and `JobService.delete_job` with cleanup-before-record-delete consistency.

- [ ] **Step 1: Write failing safety and consistency tests**

```python
@pytest.mark.parametrize("component", ["", ".", "..", "/tmp/outside"])
@pytest.mark.asyncio
async def test_invalid_storage_components_are_rejected(tmp_path, component):
    store = LocalObjectStore(tmp_path)
    with pytest.raises(UnsafeObjectPathError):
        await store.delete_job_objects(component, uuid4())

@pytest.mark.asyncio
async def test_storage_failure_preserves_job(repository, failing_store):
    service = JobService(repository, failing_store)
    job, _ = await service.create_job("dev-user-a", "key", request())
    with pytest.raises(APIError) as error:
        await service.delete_job("dev-user-a", job.id)
    assert error.value.code == "storage_unavailable"
    assert await repository.get_for_owner(job.id, "dev-user-a") == job
```

- [ ] **Step 2: Verify RED**

Run: `cd backend && python3 -m pytest tests/unit/test_local_object_store.py tests/unit/test_job_deletion.py -q`

Expected: FAIL because Object Store types do not exist.

- [ ] **Step 3: Implement safe deletion**

Resolve only `root / owner_id / str(job_id)` after validating each component. Confirm the standardized target is a descendant of standardized root. Delete a missing directory successfully. In `JobService`, verify ownership, delete objects, then delete the repository record; map filesystem errors to `503 storage_unavailable` without exposing paths.

- [ ] **Step 4: Verify GREEN and suite**

Run: `cd backend && python3 -m pytest tests/unit/test_local_object_store.py tests/unit/test_job_deletion.py -q`

Run: `cd backend && python3 -m pytest -q`

Expected: PASS.

- [ ] **Step 5: Commit**

Commit: `feat: add safe local job cleanup`

---

### Task 5: Jobs HTTP API and Contract Fixtures

**Files:**
- Create: `backend/api/app/routes/jobs.py`
- Modify: `backend/api/app/main.py`
- Modify: `backend/api/app/container.py`
- Create: `backend/contracts/fixtures/identity.json`
- Create: `backend/contracts/fixtures/job.json`
- Create: `backend/contracts/fixtures/error.json`
- Create: `backend/tests/api/test_jobs.py`
- Create: `backend/tests/api/test_job_ownership.py`
- Create: `backend/tests/contracts/test_contracts.py`
- Create: `backend/tests/contracts/test_openapi.py`

**Interfaces:**
- Produces: `POST /v1/jobs`, `GET /v1/jobs/{job_id}`, `DELETE /v1/jobs/{job_id}`, exact fixture JSON, and OpenAPI contract checks.

- [ ] **Step 1: Write failing API and contract tests**

```python
def test_create_replay_and_conflict(client, auth_headers):
    created = client.post("/v1/jobs", headers={**auth_headers, "Idempotency-Key": "key-1"}, json=payload())
    replay = client.post("/v1/jobs", headers={**auth_headers, "Idempotency-Key": "key-1"}, json=payload())
    conflict = client.post("/v1/jobs", headers={**auth_headers, "Idempotency-Key": "key-1"}, json=payload(durationSeconds=120))
    assert created.status_code == 201
    assert replay.status_code == 200
    assert replay.json() == created.json()
    assert conflict.status_code == 409

def test_foreign_owner_cannot_read_or_delete(client):
    job = create_job(client, "dev-user-a")
    assert get_job(client, job["id"], "dev-user-b").status_code == 404
    assert delete_job(client, job["id"], "dev-user-b").status_code == 404
```

Contract tests load fixtures, validate them with Pydantic, compare serialized output exactly, and assert OpenAPI contains only the five approved paths.

- [ ] **Step 2: Verify RED**

Run: `cd backend && python3 -m pytest tests/api/test_jobs.py tests/api/test_job_ownership.py tests/contracts -q`

Expected: FAIL because job routes and fixtures do not exist.

- [ ] **Step 3: Implement HTTP mapping and fixtures**

Require an ASCII `Idempotency-Key` of 1–128 visible characters. Map first creation to `201`, replay to `200`, delete to empty `204`, conflicts to `409`, invalid input to the shared `422 validation_error`, and foreign/unknown jobs to identical `404` bodies.

- [ ] **Step 4: Verify GREEN and suite**

Run: `cd backend && python3 -m pytest tests/api/test_jobs.py tests/api/test_job_ownership.py tests/contracts -q`

Run: `cd backend && python3 -m pytest -q`

Expected: PASS.

- [ ] **Step 5: Commit**

Commit: `feat: expose local jobs API contracts`

---

### Task 6: Undeployed Terraform Skeleton, Developer Guide, and Final Gate

**Files:**
- Create: `infra/terraform/modules/api/main.tf`
- Create: `infra/terraform/modules/api/variables.tf`
- Create: `infra/terraform/modules/api/outputs.tf`
- Create: `infra/terraform/modules/data/main.tf`
- Create: `infra/terraform/modules/data/variables.tf`
- Create: `infra/terraform/modules/storage/main.tf`
- Create: `infra/terraform/modules/storage/variables.tf`
- Create: `infra/terraform/environments/dev/main.tf`
- Create: `infra/terraform/environments/dev/variables.tf`
- Create: `infra/terraform/environments/dev/outputs.tf`
- Create: `backend/README.md`
- Create: `scripts/verify-backend.sh`

**Interfaces:**
- Consumes: all Stage 2 backend behavior.
- Produces: undeployed dev resource declarations, one-command backend verification, and beginner run instructions.

- [ ] **Step 1: Write failing static Terraform checks**

Add `backend/tests/contracts/test_terraform_structure.py` asserting files declare Cloud Run min instances zero, private bucket uniform access, 1-day source and 7-day result lifecycle rules, Artifact Registry, Firestore, and three distinct service account IDs; reject `roles/editor` and `roles/owner`.

- [ ] **Step 2: Verify RED**

Run: `cd backend && python3 -m pytest tests/contracts/test_terraform_structure.py -q`

Expected: FAIL because Terraform files do not exist.

- [ ] **Step 3: Add minimal Terraform and guide**

Use variables for `project_id`, Singapore-compatible region/location, billing budget thresholds `[20, 35, 50]`, and resource names. Do not include credentials, a billing account, backend state config, or any apply command in automation.

`backend/README.md` explains input/output/storage/failure ownership, venv setup, pytest, uvicorn, curl examples, and explicitly states that data is process-local and no cloud is contacted.

`scripts/verify-backend.sh` creates/reuses `backend/.venv`, installs `.[dev]`, runs pytest, imports `create_app`, and runs Terraform formatting only when `terraform` is installed; otherwise prints a clear skip.

- [ ] **Step 4: Run all final verification**

Run:

```bash
./scripts/verify-backend.sh
./scripts/verify-ios.sh
git diff --check HEAD
git status --short
```

Expected: backend tests PASS, app import PASS, all iOS tests/builds PASS, no whitespace errors, and only Task 6 files remain uncommitted.

- [ ] **Step 5: Smoke-test the server**

Start uvicorn on `127.0.0.1:8000`, wait for `/healthz`, verify its JSON, and terminate the process. Do not bind to `0.0.0.0`.

- [ ] **Step 6: Commit**

Commit: `chore: complete Stage 2 local backend`

## Completion Gate

- Backend starts locally and exposes exactly five approved endpoints.
- All backend tests, contract checks, and existing iOS verification pass.
- Auth, owner isolation, idempotency, path safety, cleanup consistency, and privacy logging are tested.
- No Google Cloud SDK is imported and no external cloud request is made.
- Terraform remains undeployed and cloud cost remains USD 0.
- Working tree is clean.
