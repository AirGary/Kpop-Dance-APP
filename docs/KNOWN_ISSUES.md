# Known Issues

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
