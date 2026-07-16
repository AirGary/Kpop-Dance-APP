# Stage Lab Backend

This directory contains the Stage 4 development API. It is intentionally local:
it accepts resumable video uploads but does not contact Google Cloud, run AI
analysis, or persist metadata after the Python process stops.

Stage 5A adds a production container and a fail-closed `cloud-bootstrap` mode.
That mode exposes `/health` for deployment checks but rejects development
Bearer identities. It does not make the local upload implementation a cloud
storage service.

Stage 5B adds a separate `cloud` mode. It verifies Firebase ID tokens, stores
upload and job metadata in Firestore, and returns a private Google Cloud Storage
resumable-session URL so video bytes travel directly from the App to Storage.
Local `development` behavior remains available and does not contact Google Cloud.

## What Goes In And Out

- Input: a development identity locally or Firebase identity in cloud mode,
  validated MP4 metadata, and resumable video bytes.
- Output: a draft analysis-job record with stable JSON field names.
- Local data: jobs stay in process memory; source bytes use an owner-isolated
  temporary root and are checked against byte count and SHA-256 before Job creation.
- Cloud data: metadata uses Firestore and video bytes go directly to private GCS.
  `/complete` checks object size without downloading the video through Cloud Run.
  The expected SHA-256 is retained as protected metadata for the asynchronous
  media preflight stage to validate before analysis begins.
- Object cleanup: upload sessions and source objects expire after 24 hours. Deleting
  a cloud Job also removes its linked source object and upload-session metadata.
- Ownership: only the user who created a job can read or delete it. Unknown and
  foreign jobs return the same `404 job_not_found` response.
- Failures: every API failure uses the shared `error.code`, `error.message`, and
  `error.requestId` envelope. Request bodies and authorization tokens are not
  logged.

## First Local Run

From the repository root:

```bash
cd backend
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest -q
.venv/bin/uvicorn api.app.main:app --host 127.0.0.1 --port 8000
```

In a second terminal, check the public endpoint:

```bash
curl http://127.0.0.1:8000/health
```

Create and then fetch a local draft job:

```bash
curl -X POST http://127.0.0.1:8000/v1/jobs \
  -H 'Authorization: Bearer dev-user-a' \
  -H 'Idempotency-Key: first-local-job' \
  -H 'Content-Type: application/json' \
  -d '{"projectId":"123e4567-e89b-12d3-a456-426614174000","sourceFingerprint":"demo:video:001","durationSeconds":90,"byteCount":1048576,"mimeType":"video/mp4"}'
```

Use the returned `id` with:

```bash
curl http://127.0.0.1:8000/v1/jobs/JOB_ID \
  -H 'Authorization: Bearer dev-user-a'
```

Stop the server with `Control-C`. Job and upload metadata disappear because this
stage uses in-memory repositories. The Terraform files under `infra/terraform`
are design scaffolding only; no deployment command is automated or required in
Stage 4.

## One-Command Check

From the repository root:

```bash
./scripts/verify-backend.sh
```

This installs local development dependencies, runs all backend tests, checks the
app import, and checks Terraform formatting only when Terraform is already
installed. It never runs `terraform apply` and never creates cloud resources.

## Stage 6 Local AI Runtime

The real-analysis worker is isolated from the FastAPI and Cloud Run environment
under `backend/workers/analysis`. It requires Homebrew Python 3.11 and FFmpeg:

```bash
brew install python@3.11 ffmpeg
./scripts/bootstrap-local-ai.sh
./scripts/verify-local-ai.sh
```

Bootstrap validates `dependency-licenses.json`, downloads the 57 exact macOS
arm64 artifacts in `requirements-macos-arm64.lock` with required SHA-256
hashes, then installs only from that local package directory. It creates only
ignored artifacts under `.local-ai/`: a Python 3.11 virtual environment, model
files, a path-free `requirements.lock`, and the runtime-capability report. It
does not install AI packages into `backend/.venv`, read a user video, contact
Google Cloud, or create paid resources.

The verified macOS 27 baseline is Python 3.11.15, FFmpeg 8.1.2, PyTorch 2.13.0,
MMCV 2.1.0, MMDetection 3.3.0, and MMPose 1.3.2. RTMDet-m and RTMPose-m use
official OpenMMLab checkpoints whose complete SHA-256 values are recorded in
`model-manifest.json`. The probe first validates these hashes, then runs both
models against a generated frame. Both checkpoint hashes are revalidated
immediately before loading. MPS is accepted only when both probes pass;
otherwise the worker performs one CPU probe and records the result in
`.local-ai/runtime-capabilities.json`. A failed probe removes the previous
capability report rather than leaving stale `ready=true` evidence.

The model manifest rejects every license except the reviewed Apache-2.0
baseline before any AI dependency is installed. Package metadata and shipped
license files were reviewed for this technical Demo; the `xtcocotools` wheel
includes MIT and BSD text even though its metadata leaves the license field
empty. This evidence is not a complete commercial legal opinion. Training-data
provenance and final transitive notices remain a separate gate before
distribution; local technical approval is not App Store legal approval.

## Local Production Container Check

Build the same Linux architecture used by Cloud Run:

```bash
cd backend
docker build --platform linux/amd64 -t stage-lab-api:stage5a .
docker run --rm -p 18080:8080 \
  -e APP_ENVIRONMENT=cloud-bootstrap \
  stage-lab-api:stage5a
```

From another terminal, verify the public health route and fail-closed identity:

```bash
curl http://127.0.0.1:18080/health
curl -i -H 'Authorization: Bearer dev-user-a' \
  http://127.0.0.1:18080/v1/me
```

The health response reports `cloud-bootstrap`; the protected route returns
`401`. Stop the foreground container with `Control-C`.

## Guarded Stage 5B Deployment

The repository includes a sequential deployment helper. It never links billing,
changes budgets, or invokes Cloud Build. It fails closed unless it is run from
the primary `main` checkout that owns the existing local Terraform state, the
JPY 1,000 budget is scoped only to the Stage Lab project, and the container
digest is tagged for the current Git HEAD.

Merge the reviewed branch before deployment. Then review and run this one-time
budget correction separately from the deployment script:

```bash
billing_account="$(
  gcloud billing projects describe stage-lab-dev-gary-202607 \
    --format='value(billingAccountName)'
)"
budget_name="$(
  gcloud billing budgets list \
    --billing-account="${billing_account#billingAccounts/}" \
    --filter='displayName="Stage Lab Dev Monthly Guardrail"' \
    --format='value(name)'
)"
gcloud billing budgets update "$budget_name" \
  --filter-projects=projects/stage-lab-dev-gary-202607
```

This keeps the existing JPY 1,000 amount and 10%, 50%, 80%, and 100%
current-spend alerts while excluding the other projects on the billing account.
Budget alerts do not impose a hard spending cap.

The Stage 5A foundation already exists in the development project, so the
normal Stage 5B sequence is:

```bash
./scripts/cloud-bootstrap.sh preflight
image_uri="$(./scripts/cloud-bootstrap.sh image)"
./scripts/cloud-bootstrap.sh plan "$image_uri"
terraform -chdir=infra/terraform/environments/dev show stage5b.tfplan
./scripts/cloud-bootstrap.sh apply
export STAGE_LAB_TEST_ID_TOKEN_A='<Firebase ID token for test user A>'
export STAGE_LAB_TEST_ID_TOKEN_B='<Firebase ID token for test user B>'
./scripts/cloud-bootstrap.sh smoke
```

`plan` accepts only an immutable Artifact Registry image tagged for the current
commit and saves the complete Cloud Run, private Storage, Firestore, IAM, and
Firebase-project proposal for inspection. `apply` rechecks the saved plan image
before changing infrastructure. Never apply the temporary preview plan produced
with the old Stage 5A image.

`smoke` requires short-lived ID tokens from two different Firebase test users.
It checks public health, invalid-token rejection, valid identities,
cross-owner `404` isolation, bucket privacy and lifecycle policies, and the
Cloud Run `0-1` instance, `1 CPU`, `512MiB` limits. Do not commit or paste the
tokens into source files.

The source and result buckets reject public access, disable soft delete, and
delete temporary objects after one and seven days respectively. Firestore TTL
removes expired upload-session records. Storage lifecycle and Firestore TTL run
asynchronously after eligibility, so they are cost-control retention rules, not
exact deletion-time guarantees. A later scheduled cleanup stage is required for
strict deadlines. No GPU or AI worker is created.

Do not run `apply` from a Git worktree that does not contain the existing local
Terraform state. Merge the reviewed branch first, then create and inspect the
saved plan from the primary checkout that owns `terraform.tfstate`.

## iOS Simulator Connection

Keep Uvicorn running on `127.0.0.1:8000`, then run the `kpop` Debug scheme on
the iPhone 17 Simulator. Import an MP4 or MOV shorter than six minutes, open its
analysis page, and tap `压缩并上传视频`. The app creates a managed highest-1080p
MP4 copy, uploads it in resumable chunks, validates it, and displays the first
eight characters of the new draft Job ID. The original imported video remains
unchanged. The separate `元数据诊断连接` card continues to test Jobs API without
uploading video bytes.
