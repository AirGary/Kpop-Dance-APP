# Re-ID Task 3 iOS Confirmation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the iOS client safely present and submit a full-screen same/different identity decision.

**Architecture:** Keep the network DTO/client, domain service, observable model, and SwiftUI presentation separate. The model owns polling and calls the service exactly once per user choice; the view owns only presentation and authenticated image rendering.

**Tech Stack:** Swift 6, SwiftUI, Observation, Swift Testing, iPhone 17 Pro Max iOS 26.5.

## Global Constraints

- State spelling is `awaitingConfirmation`; no backend or package schema changes.
- Never persist image bytes, tokens, or URLs.
- Full-screen cover only; keep project phase analyzing until result-ready import.

### Task 1: Network and domain contract

**Files:** `kpop/Core/Networking/AnalysisAPIClient.swift`, `kpop/Core/Services/AnalysisService.swift`, `kpop/Core/Services/RemoteAnalysisService.swift`, corresponding API/service tests.

- [ ] Write failing Swift Testing cases for confirmation GET decoding/path validation and POST body/header.
- [ ] Verify the tests fail because the DTO/service calls do not exist.
- [ ] Add DTOs, client requests, domain value/protocol methods, and deterministic `identity-<job>-<confirmation>-<decision>` keys.
- [ ] Run the focused API/service tests and commit.

### Task 2: Polling and presentation state

**Files:** `kpop/Views/RealAnalysisModel.swift`, `kpopTests/RealAnalysisModelTests.swift`.

- [ ] Add failing scripted-service tests: awaiting state loads once/stops polling, same and different resume, failures retain retryable state.
- [ ] Add explicit awaiting state plus submit method; do not change phase before a real result.
- [ ] Run model tests and commit.

### Task 3: Full-screen view

**Files:** create `kpop/Views/IdentityConfirmationView.swift`; modify `kpop/Views/DancerPickView.swift`; create/modify UI test target.

- [ ] Add failing view/UI assertions for full-screen presentation, both accessible controls, image placeholders, and disabled-only-while-submitting behavior.
- [ ] Implement authenticated image cards, time labels, retryable error, cancel action, and `fullScreenCover` integration.
- [ ] Run the iOS gate on iPhone 17 Pro Max iOS 26.5, update `PROJECT_STATUS.md`, and commit only after independent review.
