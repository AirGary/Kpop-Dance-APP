# Stage 3 iOS Local API Design

## Goal

Connect the SwiftUI development build running in the iOS Simulator to the
Stage 2 FastAPI server at `http://127.0.0.1:8000`. The analysis screen creates
and fetches a real draft job while preserving the existing offline demo path.

## Scope

Stage 3 includes:

- A typed Swift client for `POST /v1/jobs` and `GET /v1/jobs/{job_id}`.
- Development-only local API configuration.
- Project metadata conversion for the existing backend request contract.
- Analysis-screen loading, success, and recoverable error states.
- Persistence of the returned UUID in `DanceProject.remoteJobId`.
- Unit and integration-style URL loading tests using an injected transport.

Stage 3 excludes video upload, Google Cloud deployment, Firebase, production
authentication, AI analysis, dancer candidates, result packages, polling, and
background execution.

## Architecture

`JobsAPIClient` is a small value type that depends on an injected HTTP
transport. It owns URL construction, development authorization,
`Idempotency-Key`, JSON encoding/decoding, status-code handling, and the shared
backend error envelope. Views do not construct requests directly.

`JobCreationInput` converts an existing `DanceProject` and managed local video
file into the backend metadata contract. It uses the project UUID as the stable
Stage 3 fingerprint and idempotency source, reads byte count from file metadata,
and maps `.mp4` to `video/mp4` and `.mov` to `video/quicktime`. It rejects a
missing file, unsupported extension, duration outside `(0, 360]`, and byte count
outside `(0, 2147483648]` before networking.

`AnalysisConnectionModel` is main-actor UI state. It creates or fetches a job,
exposes idle/loading/connected/failed presentation state, and writes the remote
job ID to the project only after a successful server response. The existing
demo controls remain available because the local backend returns only a draft
job and does not yet perform analysis.

## Environment

The Debug app configuration receives `STAGE_LAB_API_BASE_URL` through the
generated Info.plist and uses `http://127.0.0.1:8000`. Staging and Release do
not contain a localhost API URL. The client is injected from the app root so
tests and previews never contact a real server.

The Stage 3 development token is `dev-user-a`. It is a local-only fixture and
must never be treated as production authentication.

## Data Flow

1. The user imports a local `.mp4` or `.mov` and opens the analysis screen.
2. The user taps `创建云分析任务`.
3. `JobCreationInput` validates project and file metadata locally.
4. `JobsAPIClient` sends `POST /v1/jobs` with the development Bearer token and
   a stable idempotency key derived from the project UUID.
5. The backend returns `201` for creation or `200` for replay.
6. The app stores the returned UUID in `DanceProject.remoteJobId`.
7. The app sends `GET /v1/jobs/{job_id}` and presents the confirmed draft state.
8. A failure leaves existing project metadata and demo navigation usable.

## Error Handling And Privacy

Backend error envelopes map to a typed client error containing only the stable
error code and safe message. Connectivity, invalid response, decoding, local
metadata, and unsupported-environment failures remain distinct. UI copy is
short and recoverable; retry repeats the same idempotency key.

The app must not log authorization, request JSON, video names, fingerprints,
absolute paths, or backend response bodies. No video bytes leave the device in
Stage 3.

## Testing And Acceptance

- Request tests assert method, path, authorization, idempotency key, and exact
  camelCase JSON without contacting the network.
- Response tests cover `201`, replay `200`, successful fetch, backend envelope,
  malformed JSON, and connectivity failure.
- Input tests cover valid `.mp4`/`.mov`, missing file, unsupported extension,
  duration boundaries, and byte-count boundaries.
- State tests prove the remote job ID is saved only after success and that a
  retry remains possible after failure.
- The existing backend suite remains green.
- `scripts/verify-ios.sh` passes Debug tests, Staging build, and Release build.
- Manual smoke verification starts FastAPI on `127.0.0.1`, launches the Debug
  app in the iPhone 17 Simulator, creates a job, and sees the connected draft
  state without changing the existing demo navigation.
