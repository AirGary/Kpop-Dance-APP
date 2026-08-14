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

## Manual Simulator visual confirmation remains unexecuted

- **Status:** pending after the automated gate is available.
- **Impact:** automated iPhone Simulator tests cannot substitute for a manual
  run of the real local video that visually confirms private crops, `same`
  tracking resumption, and `different` complete-frame fallback.
