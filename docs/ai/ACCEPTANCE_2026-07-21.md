# Stage 6 Task 9 Local AI Demo Acceptance Record

This record intentionally omits the source video title, filename, absolute
paths, candidate images, screenshots, and pairing token.

## Task

Task 9 single-video repeatable local AI chain: upload completion, candidate
detection, restart recovery, target selection, RTMPose analysis, result package
download, and iOS package consumption. No cloud GPU, account login, or paid
service was enabled.

## Completed

- The repeatable launcher starts FastAPI on loopback and creates a short-lived
  pairing file with mode `600`; the token is not printed and is removed on exit.
- Local AI uses RTMDet-m, ByteTrack, and RTMPose-m from the existing model
  manifest. The MPS `mmcv` NMS limitation is detected and safely falls back to
  CPU.
- The real smoke chain completed upload -> candidates -> restart -> target ->
  `resultReady` -> result ZIP download on a short clip derived from the local
  acceptance video.

## Verification

- Date: 2026-07-21, Asia/Tokyo.
- `./scripts/verify-local-ai.sh`: 89 worker tests passed; real detector and
  pose probe passed on CPU; MPS was rejected by the runtime probe as expected.
- `./scripts/verify-backend.sh`: 207 passed, 1 skipped; Terraform format gate
  passed.
- `./scripts/verify-ios.sh`: Swift tests and one UI launch test passed;
  Staging and Release simulator builds passed on iOS 26.5 SDK.
- Real smoke command with `LOCAL_AI_FRAME_STRIDE=30`: 1 passed in 31.35s.
- The smoke test verified at least 3 candidates and 3 representative images per
  candidate, restart recovery, one target selection, and a valid ZIP response.

## Manual Product Checks

The following remain user-facing acceptance checks and are not claimed as
automatically verified by this record:

- [ ] Candidate list and representative images visually match the video.
- [ ] Target spotlight follows the selected dancer through the clip.
- [ ] Skeleton toggle visibly turns keypoints on and off.
- [ ] Low-confidence state is visible and safely falls back.
- [ ] At least 10 visible action changes are marked and seekable.
- [ ] Difficulty and repeat information are visible.
- [ ] Speed, mirror, and loop controls work with the imported package.
- [ ] The saved Analysis Package reopens after an offline app restart.
- [ ] A real iPhone verifies video decoding and rendering; Simulator video
  frames are not sufficient for this check.

## Privacy And Cost

- No Google Cloud GPU, paid AI service, or account login was used.
- Runtime media and generated packages remain in ignored local temporary
  storage; source media is not committed.
- Pairing protection requires both the development identity and the temporary
  pairing header for protected local-AI API requests.
- Runtime logs from the model libraries contain deprecation warnings and local
  diagnostic paths; these are not acceptance artifacts and must not be copied
  into GitHub issues or screenshots.

## Next

Task 9 is ready for GitHub review and user acceptance. After the PR is merged,
the remaining work is manual Xcode/real-iPhone product acceptance, not another
automatic Task 9 implementation cycle.

## Conservative hybrid Re-ID Task 4 local acceptance

This section records the later Re-ID acceptance independently from Task 9.
It intentionally omits the source-media title, filename, absolute path,
candidate crops, local workspace paths, and pairing token.

### Automated verification

- Date: 2026-08-14, Asia/Tokyo.
- Environment: macOS local CPU; Python 3.11.15; FFmpeg 8.1.2; RTMDet-m,
  ByteTrack, and RTMPose-m from the existing approved local manifest; no cloud
  GPU, account, paid service, or additional model was enabled.
- Real smoke: `STAGE_LAB_ACCEPTANCE_VIDEO=<local ignored source>
  LOCAL_AI_FRAME_STRIDE=30 backend/.venv/bin/python -m pytest
  backend/tests/smoke/test_local_ai_real_chain.py::test_real_video_upload_candidates_restart_and_target_selection -q -s`
  passed in 155.07s. It reported 8 identity clusters (cap 8), 63.0 seconds of
  selected-cluster visible duration, 100% accepted-segment pose coverage, 99
  confirmation-boundary fragments, and exactly `manifest.json`,
  `pose-track.json`, `spotlight-track.json`, `timeline.json`, and
  `confidence.json` in the v1 ZIP. The harness asserted every encountered
  ambiguous boundary paused before a ZIP existed, then submitted `same` to
  resume from its checkpoint.
- Scripted protected-API smoke covers both `same` and `different`, each reaching
  a hash-validated five-member v1 ZIP without video or model bytes.
- `./scripts/verify-local-ai.sh`: 107 worker tests passed; CPU detector and
  pose probes passed. Model-library deprecation warnings were emitted.
- `./scripts/verify-backend.sh`: 231 passed, 1 skipped; one existing
  Starlette/httpx deprecation warning; Terraform format gate passed.
- `./scripts/verify-ios.sh`: iPhone 17 Simulator on iOS 26.5 ran the unit and
  UI suites successfully (including the identity-confirmation fixture) and
  completed Staging and Release Simulator builds.

### Remaining manual Simulator visual check

- [ ] Run the real local video through the iPhone 17 Pro Max iOS 26.5 Simulator
  and visually confirm private crops, `same` resumption, and `different`
  complete-frame fallback. Automated Simulator tests do not substitute for this
  real-media visual observation.
