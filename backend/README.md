# Stage Lab Local Backend

This directory contains the Stage 2 development API. It is intentionally local:
it does not upload videos, contact Google Cloud, run AI analysis, or persist data
after the Python process stops.

## What Goes In And Out

- Input: development Bearer identity plus validated video metadata. Video bytes
  are not accepted by this stage.
- Output: a draft analysis-job record with stable JSON field names.
- Job data: stored only in process memory and lost when the server restarts.
- Object cleanup: restricted to the configured local temporary storage root.
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
curl http://127.0.0.1:8000/healthz
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

Stop the server with `Control-C`. The job disappears because this stage uses an
in-memory repository. The Terraform files under `infra/terraform` are design
scaffolding only; no deployment command is automated or required in Stage 2.

## One-Command Check

From the repository root:

```bash
./scripts/verify-backend.sh
```

This installs local development dependencies, runs all backend tests, checks the
app import, and checks Terraform formatting only when Terraform is already
installed. It never runs `terraform apply` and never creates cloud resources.

## iOS Simulator Connection

Keep Uvicorn running on `127.0.0.1:8000`, then run the `kpop` Debug scheme on
the iPhone 17 Simulator. Import an MP4 or MOV shorter than six minutes, open its
analysis page, and tap `创建云分析任务`. A successful card shows the draft state
and the first eight characters of the server job ID. This Stage 3 flow sends
metadata only; video bytes remain on the simulator.
