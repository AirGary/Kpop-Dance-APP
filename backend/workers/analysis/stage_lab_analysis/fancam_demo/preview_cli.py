from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import json
import math
from pathlib import Path
import sys
import time

from .benchmark_cli import _components, _default_model_root
from .preview import analyze_samples, native_samples


def main():
    parser = argparse.ArgumentParser(description="Local continuous Fancam preview, not an acceptance score")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--member", choices=tuple("ABCDEFGHIJKLMNOPQRST"), default="B")
    parser.add_argument("--members", type=int, required=True)
    parser.add_argument("--duration", type=float, default=30.)
    parser.add_argument("--sample-fps", type=float, default=6.)
    parser.add_argument('--offline-trajectories', action='store_true')
    parser.add_argument('--absence-hold-seconds', type=float, default=.5)
    args = parser.parse_args()
    if not math.isfinite(args.absence_hold_seconds) or args.absence_hold_seconds < 0:
        parser.error('--absence-hold-seconds must be finite and nonnegative')
    if args.output.exists():
        parser.error("output already exists")
    if args.output.resolve() == args.source.resolve():
        parser.error("source and output must differ")
    if not args.output.parent.is_dir():
        parser.error("output directory must already exist")
    started = time.perf_counter()
    inferred_times = set()
    def progress(timestamp, count):
        print(json.dumps({"phase":"tracking", "percent":round(min(100,timestamp/args.duration*100)), "sampleCount":count}), file=sys.stderr, flush=True)
    with redirect_stdout(sys.stderr):
        detector, embedder = _components(
            _default_model_root(),
            **({'detector_threshold': .1} if args.offline_trajectories else {}))
        samples, metrics = analyze_samples(native_samples(args.source, args.duration, args.sample_fps), detector, embedder,
            member_count=args.members, member_index=ord(args.member)-ord("A"), progress=progress,
            offline_trajectories=args.offline_trajectories, on_inferred=inferred_times.add)
        print(json.dumps({"phase":"rendering", "percent":0}), file=sys.stderr, flush=True)
        from .preview_render import render_preview
        rendered = render_preview(args.source, args.output, samples, duration=args.duration,
            member_code=args.member, inferred_times=inferred_times,
            missing_policy='hold' if args.offline_trajectories else 'bridge',
            hold_seconds=args.absence_hold_seconds)
    print(json.dumps({**metrics,"render":rendered,"elapsedSeconds":round(time.perf_counter()-started,2)}), flush=True)


if __name__ == "__main__":
    main()
