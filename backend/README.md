# Stage Lab Local Backend

This directory contains the Stage 4 development API. It is intentionally local:
it accepts resumable video uploads but does not contact Google Cloud, run AI
analysis, or persist metadata after the Python process stops.

Stage 5A adds a production container and a fail-closed `cloud-bootstrap` mode.
That mode exposes `/health` for deployment checks but rejects development
Bearer identities. It does not make the local upload implementation a cloud
storage service.

## What Goes In And Out

- Input: development Bearer identity, validated MP4 metadata, and ordered 5 MiB
  upload chunks through a short-lived signed URL.
- Output: a draft analysis-job record with stable JSON field names.
- Job data: stored only in process memory and lost when the server restarts.
- Video data: stored under an owner-isolated local temporary root and checked
  against the declared byte count and SHA-256 before Job creation.
- Object cleanup: upload sessions and local source objects expire after 24 hours.
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

## Guarded Stage 5A Deployment

The repository includes a sequential deployment helper. It never links billing,
changes budgets, invokes Cloud Build, or enables Firebase. Run each command only
after the previous result has been reviewed:

```bash
./scripts/cloud-bootstrap.sh foundation
image_uri="$(./scripts/cloud-bootstrap.sh image)"
./scripts/cloud-bootstrap.sh plan "$image_uri"
terraform -chdir=infra/terraform/environments/dev show stage5a.tfplan
./scripts/cloud-bootstrap.sh apply
./scripts/cloud-bootstrap.sh smoke
```

`foundation` creates only the required service enablement and Artifact Registry
repository. `plan` saves the complete Cloud Run proposal for inspection. `apply`
accepts only that saved plan, and `smoke` verifies the public health endpoint and
that a development Bearer token is rejected.

## iOS Simulator Connection

Keep Uvicorn running on `127.0.0.1:8000`, then run the `kpop` Debug scheme on
the iPhone 17 Simulator. Import an MP4 or MOV shorter than six minutes, open its
analysis page, and tap `压缩并上传视频`. The app creates a managed highest-1080p
MP4 copy, uploads it in resumable chunks, validates it, and displays the first
eight characters of the new draft Job ID. The original imported video remains
unchanged. The separate `元数据诊断连接` card continues to test Jobs API without
uploading video bytes.
