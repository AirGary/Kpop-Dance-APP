# Local AI Demo

This is the repeatable Stage 6 Task 9 development path. It runs the existing
FastAPI API and the local RTMDet-m/ByteTrack/RTMPose-m worker on the Mac. It
does not contact Google Cloud and it does not require a user account.

## Prerequisites

- macOS 27 on Apple Silicon
- Homebrew Python 3.11 and FFmpeg
- `.local-ai/venv` and model files created by `./scripts/bootstrap-local-ai.sh`
- `backend/.venv` created by `./scripts/verify-backend.sh`; this environment starts FastAPI

The API and AI worker intentionally use separate environments: Uvicorn comes
from `backend/.venv`, while RTMDet/RTMPose run from `.local-ai/venv`.

## Start Loopback Demo

From the repository root:

```bash
./scripts/run-local-ai-demo.sh
```

The default bind is `127.0.0.1:8000`. The script creates a random short-lived
pairing token in a temporary file with mode `600`, starts the API, waits for
`/health`, and prints only the API URL and environment-file path. It never
prints the token itself. In a second terminal, source the printed environment
file before launching the Debug app. The file is deleted when the server stops.

The Debug app must receive these temporary values through the Xcode Run scheme:

- `STAGE_LAB_ENVIRONMENT=local-ai`
- `STAGE_LAB_API_BASE_URL=http://127.0.0.1:8000`
- `STAGE_LAB_PAIRING_TOKEN=<value from the temporary env file>`

The backend rejects protected requests unless both the development Bearer
identity and the matching pairing header are present.

## Real iPhone On Private LAN

Find the Mac's private IPv4 address, then bind explicitly:

```bash
./scripts/run-local-ai-demo.sh --bind 192.168.1.20
```

Only RFC1918 IPv4 addresses are accepted: `10/8`, `172.16/12`, and
`192.168/16`. Public addresses, arbitrary host names, and IPv6 are rejected by
the script. The iPhone and Mac must be on the same trusted private network.
Use the printed temporary URL and token in the Debug scheme only. Do not add
them to an Xcode user scheme, source file, issue, screenshot, or commit.

Stop with `Control-C`. The script terminates Uvicorn and removes its temporary
pairing file and runtime object directory. The local AI runtime writes video,
candidate images, proxies, and result packages only below that ignored runtime
directory.

## API Flow

1. App uploads the managed local video copy to `POST /v1/uploads` and completes it.
2. FastAPI starts detection and exposes candidates at `GET /v1/jobs/{id}/dancers`.
3. App selects one candidate at `POST /v1/jobs/{id}/target`.
4. Worker writes `analysis/result-v1.zip`; App downloads it through the protected result-content route.
5. App verifies and saves the package under Application Support for offline practice.

## Privacy Boundary

The demo is local-only. Request logs contain request metadata but must not
contain tokens, absolute paths, video bytes, candidate images, or video titles.
The model output is a technical demonstration and is not approved for App Store
distribution until model, training-data, and dependency licensing is reviewed.
