# Re-ID Task 3: iOS Identity Confirmation Design

## Goal

Present a full-screen, recoverable identity decision when a selected target analysis reaches backend state `awaitingConfirmation`.

## Confirmed UX

`DancerPickView` presents `IdentityConfirmationView` using `fullScreenCover`. The page shows the previous and candidate authenticated frame images, their time ranges, an explanation, and exactly two decisions: “是，同一位舞者” and “不是”. It returns to polling only after a successful submission; cancel and transport failures retain the page and are retryable.

## Architecture and safety

`AnalysisAPIClient` decodes the owner-scoped confirmation DTO and submits a Codable decision request with the existing authorization headers. `RemoteAnalysisService` converts it to a Sendable domain value and derives an idempotency key from job, confirmation, and decision. `RealAnalysisModel` maps `awaitingConfirmation` to one explicit state, fetches once, and stops polling until submit succeeds. Images use the existing authenticated content downloader and path validation; no token, bytes, or URL is persisted.

## Scope and constraints

- No backend, model, cloud, account, Analysis Package v1, candidate-picker layout, or portrait-follow changes.
- Use the backend’s public spelling `awaitingConfirmation` and a full-screen cover, not a sheet.
- Preserve `DanceProject.phase == .analyzing` until result import succeeds.
- Provide API, service, model, and UI accessibility regression tests; target iPhone 17 Pro Max iOS 26.5.

## Acceptance and rollback

The iOS gate must cover exact GET/POST wire contracts, protected paths, stable idempotency, same/different resume, transport retry, and full-screen accessibility IDs. Reverting this Task removes only client state and presentation; persisted backend decisions/checkpoints remain valid.
