# Offline member trajectories implementation plan

> Execute with test-driven development and scoped subagent review. No commits.

**Goal:** Add the approved opt-in offline member trajectory path and absence policy A.
**Architecture:** Reuse detector/Re-ID/forward trusted anchors; intersect independent forward/backward anonymous trajectory links, then propagate matching endpoint identities with global same-frame exclusion. Keep inference separate from identity evidence and existing model memories.
**Tech stack:** Existing Python, NumPy, SciPy, OpenCV and FFmpeg only.

## Global constraints

- Local only; no upload, commit, overwrite, KPR, new model or dependency.
- Keep all pre-existing edits and default paths unchanged.
- `member_count` is source configuration; this source uses five and B.
- Never force a member into a missing frame, learn from inferred identity, or report coverage as accuracy.

## Task 1: Trajectory stitching and integration

- [ ] Add failing synthetic checks in `backend/workers/analysis/tests/test_fancam_offline_tracker.py`.
- [ ] Implement `stitch_trajectories(observations, anchors, *, member_count)` in `backend/workers/analysis/stage_lab_analysis/fancam_demo/offline_tracker.py`. Observations are `(timestamp, detections, embeddings)` tuples; anchors are same-length member-index-to-detection-box mappings. Return same-length box mappings and inferred-member sets.
- [ ] Link recent detection endpoints with the existing Hungarian assignment dependency, private unmatched columns, geometric/scale gates and assignment ambiguity rejection. Run in both time directions and retain reciprocal links only. Matching identity anchors on a connected path may fill only real detection nodes; contradictory anchors or concurrent use of an identity reject the proposed span.
- [ ] Test missing features over a continuous path, conflicting identities, competing crossings, detector gaps, extra detections, input validation and no mutation.
- [ ] Opt-in integration in `preview.py`, `preview_cli.py`, `edgetam_preview_cli.py`. Preserve selected-body bounds, mark trajectory inference separately, and never reseed from it. Replay source frames only for newly recovered pose bounds.
- [ ] Run focused checks, then all analysis tests; independently review the combined implementation.

## Task 2: Absence A (independent renderer slice)

- [ ] First add failing checks to `backend/workers/analysis/tests/test_fancam_preview_render.py`.
- [ ] In `backend/workers/analysis/stage_lab_analysis/fancam_demo/preview_render.py`, add keyword-only `missing_policy="bridge"` and `hold_seconds=.5` to `_camera_boxes` and `render_preview`. Validate public inputs; supported policies are `bridge` (unchanged default) and `hold`.
- [ ] Hold mode: interpolate normal adjacent observations, but never interpolate across an explicit missing sample. Keep the exact last rendered camera framing for at most the configured hold measured from the last actual observation; mark inference. Then return full stage. Future samples/smoothing must not move the held camera. No compounded second hold in the geometry fallback.
- [ ] Test moving endpoints with a missing interior run, leading/trailing/long absence, exact timeout, inferred accounting, invalid options and unchanged default behavior. Include a synthetic MP4 through public render.
- [ ] Run `rtk proxy env PYTHONPATH=backend/workers/analysis .local-ai/venv/bin/python -m pytest backend/workers/analysis/tests/test_fancam_preview_render.py -q` and report RED/GREEN exits. Do not touch CLI, tracker or docs in this subtask.

## Task 3: Local evidence

- [ ] Run a new uniquely named real-source experiment with fixed five/B. Inspect second-row recovery and actual-absence segments; retain old artifacts.
- [ ] Record aggregate counts, elapsed time, process exit, output decode and visual-check limits in `docs/PROJECT_STATUS.md`; update `docs/KNOWN_ISSUES.md` if limitations remain.
- [ ] Keep Stage In Progress until genuine visual acceptance; do not equate successful encoding with continuous correct identity.
