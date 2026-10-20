# Known Issues

本桌面分支的 Fancam 限制见下方新增章节；其余内容为基线历史。本次不发布或验证 iOS/API/云端修复。

## Desktop camera stabilization remains awaiting visual acceptance (2026-10-20)

- r8 eliminates all 230 geometry-only fallback frames on the same fused input;
  2533/5360 frames (47.26%) still fall back because the B trajectory is missing.
  Identity observations/inferences remain 656/215; coverage is not accuracy.
  83/84/86s now retain local B framing; 67.5/115/160/165/170s gaps remain.
  Motion metrics improve, but contact sheets cannot establish dynamic viewing
  acceptance. Body containment overrides motion limits on abrupt movement.
  Foreground occluders and body pixels absent from the source are not repaired.
  Default bridge behavior and identity gates are unchanged; this is an offline
  desktop experiment, not an accepted product release.

## Offline member trajectories remain unaccepted (2026-10-06)

- 2026-10-11 overlap/adjacent-continuity association candidate restores B
  inference from 5 to 72 samples in a fixed 78–92s real replay; all six
  reviewed 83–88s B controls match their correct boxes. This is local evidence,
  not measured full-source identity accuracy. Full r7 completed with exit 0;
  verified 2026-10-15: inferred B 148→215, no lost/changed old B samples,
  fallback 2878→2763/5360 (51.55%); all frames decode, exit 0.
  All 67 added sample boxes and 15 matched rendered frames were inspected.
  85/87/88/89s improve, but 83s changes from close to wide; 84/86s still
  fall back. 67.5/160/165/170s gaps remain. Foreground occluders and source
  truncation remain visible; no full-source identity/full-body acceptance.
  Adjacent-frame priority can suppress stale-endpoint recovery;
  retain reciprocal links, ambiguity rejection and agreeing endpoint anchors.

- r6 full-length validation completed on 2026-10-11: exit 0, 1721.39s wall
  time; all 5360 frames decode (exit 0). Identity observations remain 656,
  inferred samples fall from 161 to 148, and wide fallback rises from 2850
  to 2878/5360 (53.69%, +28 frames). Matched five-second contact sheets show
  67.5s regressing from close to wide; 85/88/160/165/170s remain wide.
  Local camera-estimation correctness does not establish global improvement.
  The desktop branch is an experiment, not a visually accepted release.
  Sparse samples do not measure identity accuracy or full-body retention.

- Camera compensation now requires masked-background alignment improvement
  (2026-10-11). Fixed-observation/anchor real replay joins the reviewed B paths
  at 85–88s into 84.301–88.905s and rejects the .17457 false translation.
  This is a local geometry improvement, not successful identity recovery:
  inferred B samples remain 5, all six controls still lack recovered identity,
  and overall reciprocal links change from 623 to 612. Subsequent full-length
  rendering regresses coverage as recorded above; identity accuracy remains
  unmeasured. Translation-only
  photometric validation can fail on illumination changes, repeated textures,
  zoom/rotation, or insufficient unmasked background. Keep Stage unaccepted.

- 2026-10-11 current-configuration diagnostic (opening to 92.1s, exit 0)
  confirms six reviewed B detections at 83–88s are present (IoU 1 against
  prior reviewed boxes, confidence .56–.86). All six fail the existing .03
  crop-quality gate (.00536–.02717), so identity features are unavailable.
  Reciprocal paths split at 83.9/84.0 and 86.5/86.6s; the latter boundary's
  estimated camera translation is .17457 while uncorrected box-center motion
  is .03665. Edge clamping allows the forward gate (.05937 <= .06) but the
  reverse gate fails (.17617 > .06). This splits the reciprocal graph;
  surviving paths have a B anchor only before 82.716s or no anchors at all.
  Whole-frame phase correlation is not validated background motion. First
  validate camera estimate reliability; do not lower identity gates to label
  these anonymous paths. Evidence: ignored B-paths-20261011 report files.

- Earlier enhanced r5 full run is finished, exit 0 (1694.01s), and decode
  checked on 2026-10-11, exit 0. It recovers 161 inferred samples beyond
  656 identity observations, but still has 2850/5360 wide frames (53.17%).
  Keyframes at 85/88/160/165/170 seconds remain wide. Four enhancements
  have synthetic coverage (434 analysis tests passed); visual acceptance
  is still unmet. Camera compensation estimates translation only; visibility
  labels are heuristics, not measured occlusion truth. Do not tune thresholds
  again without segment-level evidence of broken paths or missing anchors.

- Full-length run exits 0 and fully decodes, but falls back on 2927/5360
  frames (54.61%). Only 81 samples are recovered beyond 656 direct observations.
  Keyframes at 85/88/165/170 seconds still show wide framing; at 160 seconds
  the occluded crop includes a foreground member. This does not meet the user's
  continuous-close-framing reference. Do not rerun the finished job unchanged;
  diagnose visible-member trajectory breaks and missing anchors next.
- The opt-in reciprocal trajectory layer and absence hold policy pass 421
  analysis tests and a scoped read-only review. A 30-second real run encodes and
  fully decodes successfully, but retains 174/900 fallback frames; ten sampled
  frames do not establish identity accuracy. Full-length validation is finished.
  Detection continuity plus agreeing endpoint anchors is a heuristic;
  ambiguous crossings, missing anchors and long detection gaps remain unknown.
  This is not a globally optimal multi-hypothesis solver or measured identity
  accuracy. Inferred observations never update identity galleries or reseed masks.
- A sandboxed real run repeatedly reports OpenVINO `Xbyak err=11`; the embedder
  converts these inference failures into missing features. That run was stopped
  and retained as a failure; the local CPU 30-second rerun outside that restriction
  succeeded. The full-length rerun is finished. A valid encode alone will
  not close the full-length second-row issue.

## EdgeTAM fusion remains experimental (2026-09-11)

- State-separation/reseed full-source experiment regresses continuity: 403/1787
  trusted samples, 39 reseeds, 2845/5360 fallback frames (53.08%) versus 2080
  previously. All frames decode, but second-row recovery remains unproven.
  Diagnose assignment vs overlap/appearance/confirmation rejection before
  relaxing gates; more nonempty masks do not establish correct identity.

- r4 rendered full-source output completes successfully (1689.74s, decode
  exit 0), but remains unaccepted: 2080/5360 fallback frames (38.81%), versus
  1963 before; 2243 observed and 1037 bridged/inferred focused frames. Local
  identity corrections do not establish overall continuous-lock success.
  Stop further threshold patches after this third attempt; review identity
  state isolation and mask re-prompting before another structural change.

- 2026-09-15 r4 gallery-learning guard improves the r3 regression but is not
  accepted: same-frame full-source comparison exits 0 in 663.23s; 899/1787
  accepted vs old baseline 1056/1787 (not accuracy). On 70–92s all 220 sample
  geometries match baseline, restoring the earlier continuity loss. Visual
  125–145s five-second samples select B instead of the old wrong member.
  Missing tracks remain elsewhere; full rendered verification is in progress.

- r3 distinctive-competitor veto has a coverage regression: full same-input
  run exited 0 in 637.18s, accepted 669/1787 vs baseline 1056/1787. Visual
  samples around 125–145s show some corrected B selections, but correct
  baseline tracks around 75–90s are absent in the new path. Do not promote
  or render this as a successful overall upgrade without resolving lost tracks.

- 2026-09-13 full-source same-frame ablation of the new competing-appearance
  veto produced identical selected boxes on all 1787 samples (1056 accepted
  in both runs, exit 0, 641.93s). It fixes a synthetic contract violation but
  does not improve this source. Five-second overlays show wrong-member identity
  boxes around 125s onward; investigate the first association/template drift
  before claiming a rendering or mask-only solution.

- Full-length B experiment finished (exit 0, 1637.43s wall time): 1963/5360
  output frames fall back (36.6%). Ten-second visual spot checks show other
  members centered and B off-center/outside the crop in later sections.
  A successful encode does not mean continuous correct identity; this output
  is for viewing current behavior only and fails Stage acceptance.

- Bounded mask-camera continuity is opt-in and not an acceptance fix. Real
  30s run on 2026-09-12 exited 0 in 294.33s but added only 3 inferred samples;
  24/900 output frames still fall back. Whole-video decode passed. The mask
  predictor is still prompted only at the opening frame: investigate reliable
  identity-reacquisition re-prompting before relaxing continuity gates. Frame
  coverage includes inference and does not establish identity accuracy.

- 2026-09-12: corrected 30s MP4 exists and all 900 frames decode successfully,
  but the original process summary/exit code was lost with its session. Visual
  spot checks still show foreground occlusion near 6s and full-stage at 29s.
  A fresh 10fps trace (exit 0) accepts B through 28.712s then rejects the tail:
  nearby detections mostly lack embeddings; one 0.767 similarity candidate
  fails the short-gap 0.8 gate. Identity-missing fusion discards mask evidence,
  and a trailing gap lacks the right endpoint needed for bounded interpolation.
  Do not resolve this by labeling propagated masks as confirmed identity or by
  weakening appearance thresholds without controlled occlusion counterexamples.

- Same-input 30s/10fps ablation isolated a template-quality contract bug:
  1194/1194 valid descriptors were below the newly introduced 0.5 focus-score
  gate (embedder validity threshold is 0.03, not a probability threshold).
  Guarded trackers accepted 62/300 samples vs 156/300 without the gate.
  The tracker now shares the embedder threshold and retains overlap protection.
  Strict reentry also preserves the strong-appearance eligibility branch while
  requiring three observations. Regression: 357 passed; video accuracy remains
  unmeasured and the corrected pipeline still requires rendered validation.
  Corrected same-input run: unguarded 156/300, strict-only 156/300,
  guard-only 197/300, guard+strict 182/300, 116.66s, exit 0.
  These are accepted tracking samples, not rendered frames or identity accuracy.

- MPS produced invalid masks even with the official frame loader; exact failing
  operator is not isolated. CPU is the experimental CLI default, not a proven
  performance solution.
- CPU mask-only 30s: 106/900 fallback frames. Detector/Re-ID geometry fusion:
  33/900 fallback frames, 100/150 accepted identity samples, 150.16s end-to-end.
  The ending still loses B; v5 remains the continuity baseline. Geometry
  acceptance and nonempty masks do not establish identity accuracy.
- Source checks at 9–14s show feet outside the original frame, so full-body
  retention cannot be measured there as though the feet were available.
- Gallery protection, optional strict three-frame reentry and WholeBody bounds
  are now implemented with tests. CPU 10fps/30s integration completed in
  280.27s, exit 0: 166/300 identity/pose samples, 294 nonempty masks,
  720/900 focused frames and 180 fallback frames. This regresses continuity
  versus the previous 33 fallback frames and is not an accepted upgrade.
  Initial-overlap/reentry contamination guards added after this run are tested
  but not included in its real-video evidence.
- Interleaved MMPose/RTMDet initially failed because pose initialization changed
  the global registry scope; scoped pose execution restores the detector scope.
  Regression reproduced before the fix and the subsequent real run completed.
- Pending: same-frame ablation of sampling/template protection/reentry before
  changing thresholds; full confirmation state machine and mask re-prompting;
  full-video identity/framing validation and peak-memory measurement.

## AI proposal acceptance remains distinct from component selection

- **Status:** active Stage 1 acceptance boundary; all 30 review scenes were explicitly accepted, and the resulting legacy truth was recoverably migrated on 2026-09-04 to exactly five stable anonymous member IDs with no within-scene duplicates.
- **Impact:** AI-generated anonymous proposal scenes are only a local ignored draft until explicitly accepted. `high` scenes may be batch-accepted, but every `review` timestamp requires explicit local acceptance; no unaccepted scene can become truth. Automated confidence must not be represented as a member identity decision or as evidence that the component-selection gate passed.
- **Next:** retain the migrated canonical truth and its ignored legacy backup. `no_safe_candidate` remains until a user-authorized aggregate evaluation against that human-accepted truth passes.

## Stage 1 component selection awaits a real aggregate evaluation

- **Status:** intentionally blocked at `no_safe_candidate`; same-run local review runner/CLI is synthetically verified on 2026-08-24, but no real source evaluation has run.
- **Impact:** the current RTMDet-m + OpenVINO 0277 + existing tracker baseline
  has hash-gated Apache-2.0 provenance and a passing local CPU probe. Local
  anonymous truth exists only in the ignored local boundary, and its real-source
  aggregate score has not been produced. Detection/embedding counts alone cannot
  establish identity accuracy, false locks, ID switches, or confirmation
  frequency, so the baseline must not be selected.
- **Next:** only after explicit user authorization, run the baseline against the
  local truth to obtain aggregate metrics, and retain `no_safe_candidate` if any
  safety threshold fails. Do not install a replacement component merely to
  advance this stage.

## Task 3 real aggregate evaluation has not run

- **Status:** same-run local review runner/CLI implementation and synthetic verification completed on 2026-08-24; no real source score has been run.
- **Impact:** the registered current baseline now has a truth-consuming direct-source
  runner and aggregate-only CLI, but no detection, identity, switch, false-lock or
  confirmation metric may be claimed until a user-authorized local run completes.
  Selection remains `no_safe_candidate`.
- **Next:** retain the existing privacy boundary and run only after explicit user
  authorization; stdout, scorecards and Git must continue to exclude frames, boxes,
  embeddings, labels and source paths.

## Current aggregate runner remains unproven on a real source

- **Status:** same-run local human review is synthetically verified on 2026-08-24. The confirmed cancellation/rejection review findings are covered: Esc cancels the run with nonzero CLI exit and no stdout, while reject remains an unconfirmed safe result. A user-authorized private aggregate run remains pending.
- **Impact:** the CLI does not accept pre-run runtime-ID mappings: it creates a per-run in-memory reviewer, while its stdout remains aggregate-only. This does not establish a real component-selection result, so it must not unlock rendering or change `no_safe_candidate`.
- **Next:** only after user authorization may a private local run be used to produce an aggregate score; retain `no_safe_candidate` unless that score passes.

## High-precision Fancam tracking fails the real five-member candidate baseline

- **Status:** mitigated for a source-specific 30-second preview on 2026-09-10,
  but not resolved for full-video Stage 1 acceptance. The older candidate path
  fragmented five dancers into eight identities; the new preview path fixes the
  configured group at five and initializes A–E left-to-right from the opening
  complete scene.
- **Impact:** B is accepted by the tracker on 129/180 samples in the first 30
  seconds. Bounded interpolation and a maximum 0.5-second camera hold now keep
  the 9:16 v5 preview framed for 900/900 output frames (620 observed and 280
  inferred/held). A 30-frame contact sheet was visually checked and stayed on B,
  but this is local preview evidence, not independently labelled identity
  accuracy. The current 0277 appearance model is documented for mostly upright
  full-body people with less than 50% occlusion, which does not cover this
  video's turning, crouching and heavy overlap. Occluded body parts and body
  parts absent from the source cannot be restored by cropping.
- **Next:** obtain user playback acceptance of the 30-second preview, then run
  and inspect the full source before Stage 1 acceptance. Benchmark a target-mask
  video tracker plus stronger Re-ID and WholeBody head/ankle framing checks
  against the existing accepted truth; do not relax 0277 thresholds and call it
  accuracy. Keep `preview_unvalidated` and the identity-evidence selection gate
  closed until independent evidence is available. Do not commit source video,
  frames, crops, embeddings or rendered media.

## Re-ID Task 4 CPU sampling baseline

- **Status:** resolved for the documented local acceptance path on 2026-08-14.
- **Impact:** the default stride 6 makes CPU target-pose analysis of the 180
  second local acceptance video exceed the smoke polling window; it must not be
  used as a bounded acceptance configuration.
- **Resolution:** use the existing local Demo baseline
  `LOCAL_AI_FRAME_STRIDE=30`. The real smoke reached `resultReady` in 155.07s
  with the required identity, confirmation, coverage, and v1-package checks.
- **Risk:** stride 30 is a local Demo sampling trade-off, not evidence of
  full-30fps pose fidelity. A product-quality performance/precision baseline
  remains future work.

## Manual Simulator visual confirmation is blocked by real app-path input

- **Status:** observed on 2026-08-14; the prescribed iPhone 17 Pro Max iOS
  26.5 Simulator run cannot reach the confirmation UI with its actual managed
  upload.
- **Evidence:** the local app imported the ignored real video from Photos,
  produced the managed compressed upload, and received 8 displayed candidate
  clusters. The persisted worker output contained 124 fragments, every
  displayed candidate cluster contained one fragment, and the identity
  decisions contained zero `awaiting_confirmation` boundaries. Target analysis
  therefore correctly reached `resultReady` without presenting a confirmation
  sheet.
- **Impact:** the existing direct-source automated smoke does not establish
  that the real iOS managed-upload path has an ambiguous identity boundary.
  Consequently this run cannot visually confirm private crops, `same` tracking
  resumption, or `different` complete-frame fallback. Fixture UI tests and
  scripted API decisions remain distinct, non-substituting evidence.
- **Next:** reopen a scoped Re-ID acceptance task only after choosing one of
  two product-level approaches: use a controlled privacy-safe acceptance asset
  that naturally creates an ambiguous boundary, or change the conservative
  clustering/sampling behavior and re-baseline its false-merge risk. Do not
  manufacture a confirmation in the runtime and present it as natural Worker
  behavior.
