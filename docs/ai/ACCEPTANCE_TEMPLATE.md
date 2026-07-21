# Stage 6 Real AI Demo Acceptance

Copy this template for a local run. Do not record the video title, source
filename, absolute paths, candidate images, tokens, or screenshots in Git.

## Run

- Date/time and timezone:
- Git commit:
- macOS / Xcode:
- iOS destination:
- Python / FFmpeg:
- Model capability: CPU or MPS:
- Frame stride:
- Runtime mode: loopback or private LAN:

## Automated Gates

- [ ] `./scripts/verify-local-ai.sh`
- [ ] `./scripts/verify-backend.sh`
- [ ] `./scripts/verify-ios.sh`
- [ ] Real API smoke: upload -> candidates -> restart -> target -> result ZIP

Record counts and elapsed time only:

- Worker tests:
- Backend tests:
- Swift/UI tests:
- Staging and Release builds:
- Real smoke elapsed time:
- Result package byte count:

## Product Checks

- [ ] Candidate list contains the expected people and representative images.
- [ ] One target dancer is selected and identity remains stable.
- [ ] Target spotlight follows the dancer.
- [ ] Skeleton toggle visibly turns keypoints on and off.
- [ ] Low-confidence state is visible and falls back safely.
- [ ] At least 10 visible action changes are marked.
- [ ] Timeline seek lands on the selected action.
- [ ] Difficulty and repeat information are visible.
- [ ] Speed, mirror, and loop controls work.
- [ ] Offline reopen loads the saved Analysis Package.

## Privacy And Cleanup

- [ ] Logs contain no token, absolute path, video title, image, or video bytes.
- [ ] Temporary runtime files are under the ignored workspace only.
- [ ] Stopping the demo removes the temporary token and runtime directory.
- [ ] No Google Cloud GPU or paid service was enabled.

## Findings

- Measured limitations:
- Unexecuted checks:
- Follow-up Task:
