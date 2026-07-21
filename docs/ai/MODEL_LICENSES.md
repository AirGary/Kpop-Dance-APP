# Local AI Model And License Record

Status: **approved for the local technical Demo only; not commercial approval**.

## Models

| Role | Model | Version | License | Checksum source |
| --- | --- | --- | --- | --- |
| Person detection | RTMDet-m person detector | `rtmdet_m_8xb32-100e_coco-obj365-person-235e8209` | Apache-2.0 artifact | `backend/workers/analysis/model-manifest.json` |
| Target pose | RTMPose-m Body8 17-keypoint estimator | `rtmpose-m_simcc-body7_pt-body7_420e-256x192-e48f03d0_20230504` | Apache-2.0 artifact | `backend/workers/analysis/model-manifest.json` |

The exact source URLs, config URLs, checkpoint SHA-256 values, provenance URLs,
and training-data names are recorded in the model manifest. The implementation
revalidates checkpoint hashes before loading.

## Runtime Dependencies

The exact Python artifacts and reviewed license evidence are recorded in
`backend/workers/analysis/dependency-licenses.json` and the lock file. The
technical Demo gate currently accepts the reviewed dependency set, including
Apache-2.0, MIT, BSD-family, and other package notices listed there.

## Distribution Gate

`commercialDistributionApproved` remains `false`. Before TestFlight or App
Store distribution, complete all of the following:

- Confirm the right to distribute each checkpoint artifact commercially.
- Review COCO, Objects365, and Body7 training-data terms and provenance.
- Generate final third-party notices from the exact shipped dependency set.
- Re-run checksum and license gates from a clean build environment.
- Obtain legal review for the complete product and model usage.
