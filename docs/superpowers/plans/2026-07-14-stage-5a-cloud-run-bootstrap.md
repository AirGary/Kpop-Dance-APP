# Stage 5A Cloud Run Bootstrap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy a secure, scale-to-zero FastAPI bootstrap service to Google Cloud Run and verify its live health, access denial, cost limits, and console visibility.

**Architecture:** Preserve the existing local FastAPI adapters while adding an explicit `cloud-bootstrap` dependency mode whose authentication adapter rejects every protected request. Build a non-root container locally, store it in Artifact Registry, and use Terraform to deploy only Stage 5A resources to Cloud Run in Singapore.

**Tech Stack:** Python 3.13, FastAPI, pytest, Docker Buildx, Terraform 1.15, Google provider 6.x, Artifact Registry, Cloud Run, Cloud Logging, Google Cloud CLI.

## Global Constraints

- Google Cloud project is exactly `stage-lab-dev-gary-202607`.
- Region is exactly `asia-southeast1`.
- Cloud Run minimum instances is `0`; maximum instances is `1`.
- Cloud Run resources are limited to `1` CPU and `512Mi` memory.
- No GPU, Firestore, Cloud Storage, Cloud Build, VPC connector, load balancer, or AI worker may be created.
- Only `GET /healthz` is intentionally usable in cloud bootstrap mode.
- Development bearer tokens must not authorize protected cloud requests.
- The existing local development API and its tests must remain operational.
- Every behavior change follows test-first RED-GREEN verification.
- Every reviewed task is committed and pushed to `origin/codex/video-practice-mvp`.

---

### Task 1: Cloud-Safe Application Bootstrap

**Files:**
- Create: `backend/api/app/adapters/auth/unavailable_auth.py`
- Modify: `backend/api/app/config.py`
- Modify: `backend/api/app/container.py`
- Modify: `backend/api/app/main.py`
- Create: `backend/tests/api/test_cloud_bootstrap.py`
- Test: `backend/tests/api/test_health.py`
- Test: `backend/tests/api/test_identity.py`

**Interfaces:**
- Produces: `Settings.from_environment() -> Settings`
- Produces: `AppContainer.for_settings(settings: Settings) -> AppContainer`
- Produces: `UnavailableAuthVerifier.verify(token: str) -> AuthenticatedUser`, which always raises `APIError(401, "unauthorized", ...)`
- Preserves: `AppContainer.development(object_storage_root: Path) -> AppContainer`

- [ ] **Step 1: Write failing cloud-mode tests**

Add tests that create a `TestClient` with `Settings(environment="cloud-bootstrap")`, assert `/healthz` returns that environment, assert `Bearer dev-user-a` receives `401 unauthorized` from `/v1/me`, and assert `create_app(Settings(environment="unknown"))` raises `ValueError`.

```python
from fastapi.testclient import TestClient
import pytest

from api.app.config import Settings
from api.app.main import create_app


def test_cloud_bootstrap_health_is_public(tmp_path):
    settings = Settings(environment="cloud-bootstrap", object_storage_root=tmp_path)
    with TestClient(create_app(settings=settings)) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "environment": "cloud-bootstrap"}


def test_cloud_bootstrap_rejects_development_identity(tmp_path):
    settings = Settings(environment="cloud-bootstrap", object_storage_root=tmp_path)
    with TestClient(create_app(settings=settings)) as client:
        response = client.get(
            "/v1/me",
            headers={"Authorization": "Bearer dev-user-a"},
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_unknown_environment_fails_closed(tmp_path):
    settings = Settings(environment="unknown", object_storage_root=tmp_path)

    with pytest.raises(ValueError, match="Unsupported environment"):
        create_app(settings=settings)
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/api/test_cloud_bootstrap.py -q
```

Expected: FAIL because the current app always builds `AppContainer.development`, so a development token succeeds and an unknown environment does not fail.

- [ ] **Step 3: Implement the deny-all verifier and environment factory**

Implement `UnavailableAuthVerifier`:

```python
from api.app.ports.auth import AuthenticatedUser
from api.app.schemas.errors import APIError


class UnavailableAuthVerifier:
    async def verify(self, token: str) -> AuthenticatedUser:
        raise APIError(401, "unauthorized", "Authentication is required.")
```

Add `Settings.from_environment()` using `APP_ENVIRONMENT` and `OBJECT_STORAGE_ROOT`, add `AppContainer.cloud_bootstrap(...)`, and route container construction through:

```python
@classmethod
def for_settings(cls, settings: Settings) -> "AppContainer":
    if settings.environment == "development":
        return cls.development(settings.object_storage_root)
    if settings.environment == "cloud-bootstrap":
        return cls.cloud_bootstrap(settings.object_storage_root)
    raise ValueError(f"Unsupported environment: {settings.environment}")
```

Change the module app construction to use environment values:

```python
resolved_settings = settings or Settings.from_environment()
resolved_container = container or AppContainer.for_settings(resolved_settings)
```

Use the same in-memory repositories and temporary object stores in cloud bootstrap mode, but inject `UnavailableAuthVerifier`. This preserves startup cleanup without exposing development authentication.

- [ ] **Step 4: Run focused and full backend tests**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/api/test_cloud_bootstrap.py tests/api/test_health.py tests/api/test_identity.py -q
cd ..
./scripts/verify-backend.sh
```

Expected: focused tests PASS and the complete backend suite PASS.

- [ ] **Step 5: Commit and push Task 1**

```bash
git add backend/api/app backend/tests/api/test_cloud_bootstrap.py
git commit -m "feat: add cloud-safe API bootstrap mode"
git push origin codex/video-practice-mvp
```

---

### Task 2: Production Backend Container

**Files:**
- Create: `backend/Dockerfile`
- Create: `backend/.dockerignore`
- Create: `backend/tests/contracts/test_container_structure.py`
- Modify: `backend/README.md`

**Interfaces:**
- Produces: image entrypoint serving `api.app.main:app` on `${PORT:-8080}`
- Consumes: `APP_ENVIRONMENT=cloud-bootstrap`
- Produces: non-root runtime user `stage-lab`

- [ ] **Step 1: Write failing container contract tests**

Create static contract tests that require a digest-pinned Python base image, a non-root `USER`, port-aware Uvicorn startup, and exclusions for tests, virtual environments, caches, local objects, and Git metadata.

```python
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[2]


def test_dockerfile_is_pinned_non_root_and_port_aware():
    source = (BACKEND_ROOT / "Dockerfile").read_text()

    assert "python:3.13-slim@sha256:" in source
    assert "USER stage-lab" in source
    assert "uvicorn api.app.main:app" in source
    assert "${PORT:-8080}" in source
    assert "--host 0.0.0.0" in source


def test_docker_context_excludes_development_and_user_data():
    patterns = (BACKEND_ROOT / ".dockerignore").read_text().splitlines()

    for required in [".venv", "tests", "**/__pycache__", ".pytest_cache", ".git", "stage-lab-objects"]:
        assert required in patterns
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/contracts/test_container_structure.py -q
```

Expected: FAIL because `backend/Dockerfile` and `backend/.dockerignore` do not exist.

- [ ] **Step 3: Implement the production image**

Use the verified multi-platform Python image digest:

```dockerfile
FROM python:3.13-slim@sha256:eb43ff125d8d58d7449dcba7d336c23bcac412f526d861db493b9994d8010280

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml ./
COPY api ./api
RUN python -m pip install --no-cache-dir . \
    && groupadd --system stage-lab \
    && useradd --system --gid stage-lab --home-dir /nonexistent stage-lab

USER stage-lab
EXPOSE 8080

CMD ["sh", "-c", "exec uvicorn api.app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
```

Document the exact local build and smoke commands in `backend/README.md`.

- [ ] **Step 4: Run contract and real container smoke tests**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/contracts/test_container_structure.py -q
docker build --platform linux/amd64 -t stage-lab-api:stage5a .
container_id=$(docker run -d --rm -p 18080:8080 -e APP_ENVIRONMENT=cloud-bootstrap stage-lab-api:stage5a)
for attempt in {1..30}; do curl --fail --silent http://127.0.0.1:18080/healthz && break; sleep 1; done
curl --silent --output /tmp/stage-lab-protected.json --write-out '%{http_code}' -H 'Authorization: Bearer dev-user-a' http://127.0.0.1:18080/v1/me
docker exec "$container_id" id -u
docker stop "$container_id"
```

Expected: health returns `{"status":"ok","environment":"cloud-bootstrap"}`, protected status is `401`, and runtime UID is not `0`.

- [ ] **Step 5: Commit and push Task 2**

```bash
git add backend/Dockerfile backend/.dockerignore backend/tests/contracts/test_container_structure.py backend/README.md
git commit -m "feat: package API for Cloud Run"
git push origin codex/video-practice-mvp
```

---

### Task 3: Stage 5A Terraform Boundary

**Files:**
- Modify: `backend/tests/contracts/test_terraform_structure.py`
- Modify: `infra/terraform/environments/dev/main.tf`
- Modify: `infra/terraform/environments/dev/variables.tf`
- Modify: `infra/terraform/environments/dev/outputs.tf`
- Modify: `infra/terraform/modules/api/main.tf`
- Modify: `infra/terraform/modules/api/variables.tf`
- Modify: `infra/terraform/modules/api/outputs.tf`
- Modify: `.gitignore`
- Leave unused and unreferenced: `infra/terraform/modules/data/*`
- Leave unused and unreferenced: `infra/terraform/modules/storage/*`

**Interfaces:**
- Consumes: `project_id`, `region`, and immutable `container_image` variables
- Produces: Terraform outputs `api_url`, `artifact_repository_id`, and `runtime_service_account`
- Produces: Cloud Run service `stage-lab-api` and Artifact Registry repository `stage-lab-api`

- [ ] **Step 1: Replace legacy infrastructure tests with Stage 5A tests**

Tests must assert all of the following:

```python
assert '"run.googleapis.com"' in environment_source
assert '"artifactregistry.googleapis.com"' in environment_source
assert 'source = "../../modules/data"' not in environment_source
assert 'source = "../../modules/storage"' not in environment_source
assert "min_instance_count = 0" in api_source
assert "max_instance_count = 1" in api_source
assert 'cpu    = "1"' in api_source
assert 'memory = "512Mi"' in api_source
assert 'APP_ENVIRONMENT' in api_source
assert 'value = "cloud-bootstrap"' in api_source
assert 'path = "/healthz"' in api_source
assert 'role     = "roles/run.invoker"' in api_source
assert 'member   = "allUsers"' in api_source
assert "gpu" not in combined_source.lower()
assert "roles/editor" not in combined_source
assert "roles/owner" not in combined_source
```

Also assert an Artifact Registry cleanup policy deletes untagged images older than seven days.

- [ ] **Step 2: Run the infrastructure contract and verify RED**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/contracts/test_terraform_structure.py -q
```

Expected: FAIL because the current environment still references Firestore and Storage and lacks required API enablement, public invoker IAM, probes, cloud environment, timeout, and image cleanup.

- [ ] **Step 3: Implement the minimal Stage 5A Terraform graph**

In the dev environment, enable only:

```hcl
locals {
  required_services = toset([
    "artifactregistry.googleapis.com",
    "iam.googleapis.com",
    "run.googleapis.com",
  ])
}

resource "google_project_service" "required" {
  for_each = local.required_services

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}
```

Remove `module "data"` and `module "storage"` from the dev root. Keep their source files for Stage 5B, but ensure Terraform cannot instantiate them in 5A.

Add Cloud Run runtime constraints:

```hcl
template {
  service_account                  = google_service_account.api.email
  timeout                          = "30s"
  max_instance_request_concurrency = 20

  scaling {
    min_instance_count = 0
    max_instance_count = 1
  }

  containers {
    image = var.container_image

    env {
      name  = "APP_ENVIRONMENT"
      value = "cloud-bootstrap"
    }

    resources {
      cpu_idle          = true
      startup_cpu_boost = false
      limits = {
        cpu    = "1"
        memory = "512Mi"
      }
    }

    startup_probe {
      initial_delay_seconds = 0
      timeout_seconds       = 2
      period_seconds        = 3
      failure_threshold     = 10

      http_get {
        path = "/healthz"
      }
    }
  }
}
```

Add `google_cloud_run_v2_service_iam_member` for `roles/run.invoker` and `allUsers`. Add a seven-day untagged-image cleanup policy to Artifact Registry. Add `.terraform/`, `*.tfstate`, `*.tfstate.*`, and `*.tfplan` to `.gitignore` while preserving the provider lock file for commit.

- [ ] **Step 4: Format, initialize, validate, and run tests**

Run:

```bash
terraform -chdir=infra/terraform fmt -recursive
terraform -chdir=infra/terraform/environments/dev init -backend=false
terraform -chdir=infra/terraform/environments/dev validate
./scripts/verify-backend.sh
```

Expected: formatting and validation succeed, and the complete backend suite passes.

- [ ] **Step 5: Commit and push Task 3**

```bash
git add .gitignore backend/tests/contracts/test_terraform_structure.py infra/terraform
git commit -m "feat: constrain Stage 5A cloud infrastructure"
git push origin codex/video-practice-mvp
```

---

### Task 4: Guarded Deployment Workflow

**Files:**
- Create: `scripts/cloud-bootstrap.sh`
- Create: `backend/tests/contracts/test_cloud_script.py`
- Modify: `backend/README.md`

**Interfaces:**
- Produces commands: `foundation`, `image`, `plan IMAGE_DIGEST_URI`, `apply`, and `smoke`
- Persists local reviewed plan: `infra/terraform/environments/dev/stage5a.tfplan`
- Produces immutable image URI on stdout from `image`

- [ ] **Step 1: Write failing deployment-script contract tests**

Require the script to use the fixed project/region, `linux/amd64`, an immutable digest lookup, a saved Terraform plan, live health and `401` checks, and no automatic approval:

```python
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "cloud-bootstrap.sh"


def test_cloud_script_has_guarded_commands():
    source = SCRIPT.read_text()

    assert "stage-lab-dev-gary-202607" in source
    assert "asia-southeast1" in source
    assert "--platform linux/amd64" in source
    assert "image_summary.digest" in source
    assert "stage5a.tfplan" in source
    assert "/healthz" in source
    assert "/v1/me" in source
    assert "-auto-approve" not in source
```

- [ ] **Step 2: Run the script test and verify RED**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/contracts/test_cloud_script.py -q
```

Expected: FAIL because `scripts/cloud-bootstrap.sh` does not exist.

- [ ] **Step 3: Implement explicit guarded subcommands**

The script must use `set -euo pipefail`, verify `gcloud`, `docker`, and `terraform`, and implement:

- `foundation`: initialize Terraform and apply only required services plus the Artifact Registry repository.
- `image`: configure Artifact Registry authentication, build and push `linux/amd64` with the current Git SHA tag, resolve its registry digest, and print `asia-southeast1-docker.pkg.dev/stage-lab-dev-gary-202607/stage-lab-api/api@sha256:...`.
- `plan IMAGE_DIGEST_URI`: save a Terraform plan to `stage5a.tfplan` using the immutable digest URI.
- `apply`: require the saved plan and invoke `terraform apply stage5a.tfplan` without `-auto-approve`.
- `smoke`: read `api_url`, require `/healthz` status `200` with `cloud-bootstrap`, and require `/v1/me` with a development token to return `401`.

The script must never link billing, create budgets, create a Firebase project, or invoke Cloud Build.

- [ ] **Step 4: Verify script syntax and all local checks**

Run:

```bash
bash -n scripts/cloud-bootstrap.sh
./scripts/verify-backend.sh
git diff --check
```

Expected: shell syntax succeeds, all backend and contract tests pass, and Git reports no whitespace errors.

- [ ] **Step 5: Commit and push Task 4**

```bash
git add scripts/cloud-bootstrap.sh backend/tests/contracts/test_cloud_script.py backend/README.md
git commit -m "feat: add guarded Cloud Run deployment workflow"
git push origin codex/video-practice-mvp
```

---

### Task 5: Deploy, Verify, And Demonstrate Stage 5A

**Files:**
- Modify only if observed commands differ: `backend/README.md`
- Do not commit: Terraform state, saved plan, local image layers, access tokens, or Google credentials

**Interfaces:**
- Consumes: the guarded workflow from Task 4
- Produces: live `api_url`, deployed Cloud Run revision, Artifact Registry digest, and verification evidence

- [ ] **Step 1: Run fresh local verification**

Run:

```bash
./scripts/verify-backend.sh
./scripts/verify-ios.sh
docker run --rm hello-world
```

Expected: backend tests pass, iOS Debug/Staging/Release verification passes, and Docker prints `Hello from Docker!`.

- [ ] **Step 2: Create only the registry foundation**

Run:

```bash
./scripts/cloud-bootstrap.sh foundation
```

Then verify enabled services and repository:

```bash
gcloud services list --enabled --project=stage-lab-dev-gary-202607 --filter='name:(run.googleapis.com OR artifactregistry.googleapis.com OR iam.googleapis.com)'
gcloud artifacts repositories describe stage-lab-api --location=asia-southeast1 --project=stage-lab-dev-gary-202607
```

Expected: only the required APIs are enabled by this stage and the repository has its cleanup policy.

- [ ] **Step 3: Build and push one immutable image**

Run:

```bash
image_uri=$(./scripts/cloud-bootstrap.sh image)
printf '%s\n' "$image_uri"
```

Expected: the output ends in `@sha256:<64 lowercase hexadecimal characters>`.

- [ ] **Step 4: Generate and inspect the Terraform plan before deployment**

Run:

```bash
./scripts/cloud-bootstrap.sh plan "$image_uri"
terraform -chdir=infra/terraform/environments/dev show stage5a.tfplan
terraform -chdir=infra/terraform/environments/dev show -json stage5a.tfplan > /tmp/stage5a-plan.json
```

Review resource addresses and reject the plan if it includes Firestore, Storage buckets, GPU, VPC, load balancer, Cloud SQL, or more than one Cloud Run service.

- [ ] **Step 5: Apply the reviewed plan and run live smoke tests**

Run:

```bash
./scripts/cloud-bootstrap.sh apply
./scripts/cloud-bootstrap.sh smoke
```

Expected: HTTPS health succeeds and a development bearer token receives `401`.

- [ ] **Step 6: Verify live cost and security settings independently**

Run:

```bash
gcloud run services describe stage-lab-api \
  --project=stage-lab-dev-gary-202607 \
  --region=asia-southeast1 \
  --format='yaml(status.url,spec.template.spec.containerConcurrency,spec.template.metadata.annotations,spec.template.spec.containers)'
gcloud billing budgets list \
  --billing-account=0172B5-DB982A-9B6914 \
  --format='yaml(displayName,amount,budgetFilter.projects,thresholdRules)'
```

Expected: Cloud Run reports the intended image and limits with no GPU, and the Stage Lab budget reports `JPY 1000` plus the four thresholds.

- [ ] **Step 7: Show the deployed interface**

Open the authenticated Google Cloud Console pages for Cloud Run, Artifact Registry, Logs Explorer, and Billing Budgets. Show the user the live `/healthz` URL and explain which resources exist, which remain intentionally absent, and where current cost is visible.

- [ ] **Step 8: Record any command correction, verify, commit, and push**

If deployment revealed a documentation mismatch, update only the exact command in `backend/README.md`, rerun `./scripts/verify-backend.sh`, commit it, and push. If no tracked file changed, do not create an empty commit.

Final repository checks:

```bash
git status --short --branch
git log -5 --oneline --decorate
git ls-remote origin refs/heads/codex/video-practice-mvp
```

Expected: worktree clean and remote branch points to the local `HEAD`.
