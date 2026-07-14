# Stage 5B Cloud Data Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the fail-closed Cloud Run bootstrap with authenticated, owner-isolated Firestore metadata and direct resumable uploads to private Cloud Storage.

**Architecture:** Keep the current FastAPI ports and local adapters for development. Add production Firebase Auth, Firestore repository, and Cloud Storage adapters selected only by `APP_ENVIRONMENT=cloud`; Terraform provisions private short-lived buckets and least-privilege service accounts. No AI worker or GPU is created in this stage.

**Tech Stack:** FastAPI, Pydantic, Firebase Admin, Google Cloud Firestore, Google Cloud Storage, Terraform, pytest.

## Global Constraints

- Google Cloud project is supplied explicitly; no Terraform project default.
- Region and data location remain `asia-southeast1`.
- Source objects expire after 1 day; result objects expire after 7 days.
- Buckets enforce uniform access and public access prevention.
- Cloud Run remains public only at the network layer; protected API routes require a valid Firebase ID token.
- Cloud Run minimum instances remain 0 and maximum instances remain 1.
- No GPU, Workflows, Cloud Tasks, APNs, AI model, or paid music service is added.
- Local development behavior and existing API contracts remain available.

---

### Task 1: Provision Private Data Resources

**Files:**
- Modify: `infra/terraform/environments/dev/main.tf`
- Modify: `infra/terraform/environments/dev/variables.tf`
- Modify: `infra/terraform/environments/dev/outputs.tf`
- Modify: `infra/terraform/modules/storage/main.tf`
- Modify: `infra/terraform/modules/storage/variables.tf`
- Modify: `infra/terraform/modules/data/main.tf`
- Modify: `infra/terraform/modules/data/variables.tf`
- Modify: `infra/terraform/modules/api/main.tf`
- Modify: `infra/terraform/modules/api/variables.tf`
- Test: `backend/tests/contracts/test_terraform_structure.py`

**Interfaces:**
- Consumes: explicit project ID, region, immutable API image digest, globally unique bucket names.
- Produces: source bucket, result bucket, Firestore database, API runtime environment variables, and least-privilege IAM bindings.

- [ ] Add failing contract tests for enabled Storage/Firestore APIs, module wiring, lifecycle rules, public access prevention, owner-only runtime roles, and absence of GPU resources.
- [ ] Run `backend/.venv/bin/python -m pytest backend/tests/contracts/test_terraform_structure.py -q` and confirm the new tests fail for missing Stage 5B wiring.
- [ ] Wire the storage and data modules, pass bucket/database configuration to Cloud Run, and grant only object/Firestore access needed by the API.
- [ ] Run the Terraform contract tests, `terraform fmt -check -recursive infra/terraform`, `terraform init -backend=false`, and `terraform validate`.

### Task 2: Verify Firebase Identity

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/api/app/config.py`
- Create: `backend/api/app/adapters/auth/firebase_auth.py`
- Modify: `backend/api/app/container.py`
- Test: `backend/tests/unit/test_firebase_auth.py`
- Test: `backend/tests/contracts/test_container_structure.py`

**Interfaces:**
- Consumes: Firebase ID token and configured Google Cloud project ID.
- Produces: `AuthenticatedUser(user_id=<firebase uid>)` or the existing safe `401 unauthorized` envelope.

- [ ] Add failing tests for valid UID extraction, expired/invalid token rejection, missing UID rejection, and cloud container selection.
- [ ] Run the focused tests and confirm failure because the adapter does not exist.
- [ ] Add Firebase Admin initialization behind an injectable token decoder and select it only in cloud mode.
- [ ] Run focused tests and the complete backend suite.

### Task 3: Persist Uploads And Jobs In Firestore

**Files:**
- Create: `backend/api/app/adapters/repositories/firestore_upload_repository.py`
- Create: `backend/api/app/adapters/repositories/firestore_job_repository.py`
- Modify: `backend/api/app/container.py`
- Test: `backend/tests/unit/test_firestore_upload_repository.py`
- Test: `backend/tests/unit/test_firestore_job_repository.py`

**Interfaces:**
- Consumes: the existing `UploadRepository` and `JobRepository` protocols.
- Produces: transactional owner-isolated documents under `uploads/{uploadId}` and `jobs/{jobId}`, preserving idempotency behavior across Cloud Run restarts.

- [ ] Add failing repository contract tests using an injectable Firestore gateway; test ownership, compare-and-set offset updates, idempotency conflicts, expiration queries, and deletion.
- [ ] Run focused tests and confirm failure because the adapters do not exist.
- [ ] Implement adapters without logging tokens, fingerprints, object paths, or request bodies.
- [ ] Run focused tests and the complete backend suite.

### Task 4: Upload Directly To Private Cloud Storage

**Files:**
- Create: `backend/api/app/adapters/storage/gcs_upload_object_store.py`
- Modify: `backend/api/app/schemas/uploads.py`
- Modify: `backend/api/app/services/upload_service.py`
- Modify: `backend/api/app/routes/uploads.py`
- Modify: `backend/api/app/container.py`
- Test: `backend/tests/unit/test_gcs_upload_object_store.py`
- Test: `backend/tests/api/test_cloud_uploads.py`

**Interfaces:**
- Consumes: authenticated owner, upload metadata, SHA-256, and private source bucket.
- Produces: a short-lived Google Cloud Storage resumable session URL; video bytes never pass through FastAPI.

- [ ] Add failing tests for owner-prefixed object names, 24-hour metadata, resumable session creation, object size/hash verification, idempotent completion, and foreign-owner isolation.
- [ ] Run focused tests and confirm failure because cloud upload support does not exist.
- [ ] Implement a cloud upload strategy while retaining the existing local chunk routes for development.
- [ ] Run focused tests, the complete backend suite, OpenAPI contract tests, and a container smoke test.

### Task 5: Safe Deployment Gate

**Files:**
- Modify: `scripts/cloud-bootstrap.sh`
- Modify: `backend/README.md`
- Test: `backend/tests/contracts/test_cloud_script.py`

**Interfaces:**
- Consumes: reviewed immutable container digest and explicit bucket names.
- Produces: saved Terraform plan, human-readable cost-sensitive resource summary, and authenticated smoke-test instructions.

- [ ] Add failing script contract tests that require a saved plan and prohibit implicit apply.
- [ ] Update the helper to create and inspect a Stage 5B plan without enabling GPU resources.
- [ ] Run all repository verification scripts.
- [ ] Inspect `terraform show` before any apply; apply only the saved plan, then verify buckets are private, lifecycle policies exist, Cloud Run scales to zero, and foreign identities cannot read another owner's records.

