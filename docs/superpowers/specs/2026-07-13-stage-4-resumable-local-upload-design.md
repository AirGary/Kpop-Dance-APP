# Stage 4 Resumable Local Upload Design

## Goal

Add a production-shaped, locally runnable video upload flow. The iOS Debug app
creates a highest-1080p H.264 MP4 copy, uploads it to FastAPI in resumable
chunks, completes server validation, and receives a draft analysis job. No
Google Cloud resource is created and cloud cost remains zero.

## Scope

Stage 4 includes:

- Owner-isolated upload sessions with short-lived upload tokens.
- Ordered 5 MiB chunk uploads with offset discovery and resume.
- A 24-hour upload-session lifetime and expired-object cleanup.
- Server-side size and SHA-256 validation before job creation.
- iOS 1080p H.264 export, SHA-256 calculation, chunk progress, retry, and local
  staging-file cleanup.
- Analysis-screen compression/upload/validation states.
- Wi-Fi-first networking with explicit one-time cellular permission.

Stage 4 excludes Google Cloud deployment, Cloud Storage SDKs, Firebase Auth,
background URLSession, push notifications, AI detection, dancer candidates,
and result download.

## Upload API

All authenticated endpoints use the Stage 2 development bearer identity and
shared error envelope. JSON fields remain camelCase.

### Create Session

`POST /v1/uploads` requires an `Idempotency-Key` and accepts:

```json
{
  "projectId": "uuid",
  "sourceFingerprint": "sha256-or-stable-fingerprint",
  "durationSeconds": 90,
  "byteCount": 10485760,
  "mimeType": "video/mp4",
  "sha256": "64-lowercase-hex"
}
```

It returns `201` for a new session and `200` for an identical replay:

```json
{
  "uploadId": "uuid",
  "uploadUrl": "http://127.0.0.1:8000/v1/uploads/uuid/content?token=opaque",
  "expiresAt": "RFC3339 UTC",
  "chunkSize": 5242880,
  "offset": 0
}
```

The token is random, stored only as a SHA-256 digest, bound to one upload, and
never logged. Changed-body idempotency replay returns `409`.

### Discover Offset

`HEAD <uploadUrl>` requires no bearer token. A valid unexpired token returns
`204` with `Upload-Offset`, `Upload-Length`, and `Upload-Expires` headers.

### Upload Chunk

`PUT <uploadUrl>` requires `Content-Range: bytes start-end/total`. The body
length must match the range, `start` must equal the committed offset, `total`
must equal the declared byte count, and each non-final chunk must be no larger
than 5 MiB. Accepted partial data returns `308` and `Upload-Offset`; the final
chunk returns `201` and the final offset. Replaying the immediately previous
accepted range is idempotent only when its bytes match the stored bytes.

### Complete Session

`POST /v1/uploads/{upload_id}/complete` requires bearer auth and an
`Idempotency-Key`. It verifies ownership, full byte count, and SHA-256, then
creates or replays one draft Job and returns the existing `JobResponse` with
`201` or `200`. Incomplete uploads return `409 upload_incomplete`; checksum
mismatch returns `422 checksum_mismatch` and deletes the invalid object.

## Backend Architecture

`UploadService` contains validation, ownership, idempotency, expiry, offset,
and completion rules. It depends on an `UploadRepository`, an `UploadObjectStore`,
a clock, and the existing `JobService`. Routes only map HTTP headers/statuses.

The development repository is in memory. `LocalUploadObjectStore` writes under
`<object-root>/<owner-id>/uploads/<upload-id>/source.mp4`, validates every path
component, appends through a temporary file handle, and never loads the full
video into memory. Cleanup deletes expired upload records and objects before
session operations and at app startup. Completed source objects remain subject
to the existing 24-hour policy for future analysis; Stage 4 does not delete
them immediately after Job creation.

## iOS Architecture

`VideoCompressionService` exports the imported local video with
`AVAssetExportPreset1920x1080`, H.264-compatible MP4 output, and no modification
to the original. The managed staging location is
`Application Support/UploadStaging/<project-id>.mp4`.

`UploadAPIClient` owns create, HEAD, PUT, and complete contracts. It uses an
injected transport for tests and never logs request URLs because signed tokens
are query parameters. `ResumableUploadCoordinator` owns compression, hashing,
offset discovery, chunk reads, progress, retries, and cleanup.

`DanceProject` gains migration-safe optional upload metadata: remote upload ID,
confirmed offset, and upload expiry. A failed or interrupted upload preserves
the compressed staging file and metadata. A successful completion stores the
remote Job ID, clears upload metadata, and deletes the compressed staging file.

The default URLSession rejects expensive cellular access. A one-time user
confirmation creates a session with expensive access enabled for that upload;
the preference is not persisted globally.

## UI States

The analysis page presents:

- Ready: `压缩并上传视频`.
- Compressing: indeterminate progress and cancel disabled for Stage 4.
- Hashing: local validation message.
- Uploading: byte-based percentage and confirmed offset.
- Validating: server checksum/completion message.
- Completed: draft Job ID and confirmation that only the compressed copy was
  uploaded.
- Recoverable failure: safe message and `继续上传`.

The existing metadata-only connection card remains available as a developer
diagnostic, and the fake dancer/result navigation remains unchanged.

## Security And Privacy

- Duration must be in `(0, 360]`, bytes in `(0, 2147483648]`, MIME exactly
  `video/mp4`, and SHA-256 exactly 64 lowercase hex characters.
- Unknown, expired, invalid-token, and foreign-owner upload access does not
  expose another user's metadata or filesystem path.
- Logs exclude authorization, signed URLs, tokens, request bodies, video names,
  fingerprints, hashes, and absolute paths.
- A checksum mismatch deletes invalid server bytes before returning an error.
- Low-level Codex log insertion protection remains outside app behavior and
  must remain active during verification.

## Testing And Acceptance

- Backend tests cover create/replay/conflict, auth, owner isolation, token
  rejection, ordered chunks, duplicate chunk replay, offset HEAD, expiry,
  incomplete completion, checksum mismatch cleanup, successful job creation,
  and 24-hour cleanup.
- Object-store tests cover traversal rejection, bounded memory behavior,
  append/read verification, and deletion.
- iOS tests cover compression configuration, managed staging paths, exact HTTP
  contracts, cellular policy, resume offset, progress, retries, persistence,
  and staging cleanup.
- A real local smoke test uploads a generated or imported MP4 in multiple
  chunks, resumes after interruption, completes with matching SHA-256, and
  fetches the returned Job.
- `scripts/verify-backend.sh` and `scripts/verify-ios.sh` pass.
- Debug contains the local endpoint; Staging and Release contain none.
- Google Cloud remains undeployed and no cloud request is made.
