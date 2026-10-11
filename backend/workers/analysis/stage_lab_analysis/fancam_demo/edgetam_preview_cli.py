"""Experimental mask/identity/WholeBody preview; accuracy not yet validated.

Run in a dedicated process with the reviewed EdgeTAM checkout on PYTHONPATH.
"""
import argparse
from contextlib import redirect_stdout
import json
import math
from pathlib import Path
import sys
import time
from unittest.mock import patch

import cv2
import numpy as np
import torch
import timm

from ..detection import NormalizedBox
from ..pose import RTMPoseEstimator
from ..runtime_probe import load_model_manifest, resolve_model_checkpoint, resolve_model_config
from .benchmark_cli import _components, _default_model_root
from .lazy_frames import LazyFrames
from .preview_render import render_preview
from .preview import analyze_samples, native_samples
from .mask_fusion import validated_body_box, MaskContinuity
from .mask_reseed import propagate_with_reseeds


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--checkpoint', type=Path, required=True)
    parser.add_argument('--duration', type=float, default=30)
    parser.add_argument('--sample-fps', type=float, default=10)
    parser.add_argument('--member', default='B', choices=tuple('ABCDE'))
    parser.add_argument('--device', default='cpu', choices=('cpu','mps'))
    parser.add_argument('--identity-fusion', action='store_true',
                        help='Experimental detector/ReID geometry validation')
    parser.add_argument('--wholebody', action='store_true',
                        help='WholeBody bounds and strict multi-frame identity re-entry')
    parser.add_argument('--mask-continuity', action='store_true',
                        help='Experimental bounded camera inference during identity gaps')
    parser.add_argument('--identity-state-separation', action='store_true')
    parser.add_argument('--reseed-on-reacquire', action='store_true')
    parser.add_argument('--offline-trajectories', action='store_true')
    parser.add_argument('--members', type=int, help='Source-configured group size')
    parser.add_argument('--absence-hold-seconds', type=float, default=.5)
    args = parser.parse_args()
    if not math.isfinite(args.absence_hold_seconds) or args.absence_hold_seconds < 0:
        parser.error('--absence-hold-seconds must be finite and nonnegative')
    if args.members is not None and not 1 <= args.members <= 20:
        parser.error('--members must be between 1 and 20')
    if args.offline_trajectories and (args.members is None or not args.identity_fusion):
        parser.error('--offline-trajectories requires --members and --identity-fusion')
    if args.offline_trajectories and args.mask_continuity:
        parser.error('offline absence holds framing; do not combine with --mask-continuity')
    if args.identity_state_separation and not args.wholebody:
        parser.error('--identity-state-separation requires --wholebody')
    if args.reseed_on_reacquire and not (args.identity_state_separation or args.offline_trajectories):
        parser.error('--reseed-on-reacquire requires --identity-state-separation')
    if args.mask_continuity and not args.identity_fusion:
        parser.error('--mask-continuity requires --identity-fusion')
    if args.wholebody and not args.identity_fusion:
        parser.error('--wholebody requires --identity-fusion')
    if args.output.exists() or not args.output.parent.is_dir():
        parser.error('output must be a new file in an existing directory')
    start = time.perf_counter()
    frames = LazyFrames(args.source, args.duration, args.sample_fps)
    samples = []
    inferred_times = set()
    trajectory_inferred_times = set()
    mask_inferred_count = 0
    continuity = MaskContinuity() if args.mask_continuity else None
    nonempty_masks = 0
    recoveries = []
    reseed_count = 0
    torch.set_num_threads(4)
    try:
        with redirect_stdout(sys.stderr):
            detector, embedder = _components(
                _default_model_root(),
                **({'detector_threshold': .1} if args.offline_trajectories else {}))
            cap = cv2.VideoCapture(str(args.source))
            ok, frame = cap.read()
            cap.release()
            if not ok:
                raise ValueError('initial frame missing')
            detections = list(detector.detect(frame))
            if args.members is not None:
                if len(detections) < args.members:
                    raise ValueError('configured group is incomplete in opening frame')
                detections = sorted(detections, key=lambda d: -d.confidence)[:args.members]
            detections.sort(key=lambda d: d.box.x + d.box.width / 2)
            index = ord(args.member)-ord('A')
            if index >= len(detections):
                raise ValueError('selected member missing in opening frame')
            box = detections[index].box
            identity_samples = None
            identity_report = None
            if args.identity_fusion:
                pose_estimator = None
                if args.wholebody:
                    import mmpose
                    root = _default_model_root()
                    manifest = load_model_manifest(Path(__file__).resolve().parents[2] / 'model-manifest.json')
                    spec = next(m for m in manifest['models'] if m['role'] == 'pose')
                    pose_estimator = RTMPoseEstimator(
                        config=str(resolve_model_config(spec, model_root=root,
                            package_root=Path(mmpose.__file__).resolve().parent)),
                        checkpoint=str(resolve_model_checkpoint(spec, model_root=root)),
                        expected_sha256=spec['sha256'], device='cpu')
                identity_samples, identity_report = analyze_samples(
                    native_samples(args.source, args.duration, args.sample_fps),
                    detector, embedder, member_count=len(detections), member_index=index,
                    pose_estimator=pose_estimator, strict_reentry=args.wholebody,
                    separate_identity=args.identity_state_separation,
                    offline_trajectories=args.offline_trajectories,
                    replay_frames=lambda: native_samples(args.source, args.duration, args.sample_fps),
                    on_inferred=trajectory_inferred_times.add,
                    on_reacquired=lambda t,b: recoveries.append((t,b)),
                    progress=lambda t,n: print(json.dumps({'phase':'identity_check',
                        'seconds':round(t,2),'samples':n}),flush=True))
                del pose_estimator
            del detector, embedder, frame
            from sam2.build_sam import build_sam2_video_predictor
            original = timm.create_model
            # The full checkpoint is loaded strictly immediately afterwards.
            # Avoid an unnecessary separate pretrained-backbone download.
            with patch('sam2.modeling.backbones.timm.create_model',
                       side_effect=lambda *a,**kw:original(*a,**dict(kw,pretrained=False))):
                model = build_sam2_video_predictor('configs/edgetam.yaml',str(args.checkpoint),
                    device=args.device,apply_postprocessing=False)
            with torch.inference_mode():
                with patch('sam2.sam2_video_predictor.load_video_frames',
                           return_value=(frames,frames.height,frames.width)):
                    state = model.init_state('runtime',offload_video_to_cpu=True,
                                             offload_state_to_cpu=True)
                prompt = np.array([max(0,box.x-.15*box.width)*frames.width,
                    max(0,box.y-.05*box.height)*frames.height,
                    min(1,box.x+1.15*box.width)*frames.width,
                    min(1,box.y+1.05*box.height)*frames.height])
                prompts = {0: prompt}
                if args.reseed_on_reacquire:
                    for t, recovered in recoveries:
                        sample_index = round(t*frames.sample_fps)
                        sampled_at = round(sample_index*frames.fps/frames.sample_fps)/frames.fps
                        if (0 < sample_index < len(frames)
                                and abs(t-sampled_at) <= 1.01/frames.fps):
                            # Tight detection box, not pose-expanded multi-person region.
                            prompts[sample_index] = np.array([recovered.x*frames.width,
                                recovered.y*frames.height,
                                (recovered.x+recovered.width)*frames.width,
                                (recovered.y+recovered.height)*frames.height])
                reseed_count = len(prompts)-1
                for i, _, masks in propagate_with_reseeds(model, state, prompts, len(frames)):
                    if i in prompts and i > 0 and continuity is not None:
                        continuity = MaskContinuity()
                    mask = (masks[0,0]>0).cpu().numpy()
                    # Remove disconnected speckles before measuring the body.
                    # This experiment does not interpret area as identity.
                    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8),8)
                    if n > 1:
                        component = 1+int(np.argmax(stats[1:,cv2.CC_STAT_AREA]))
                        mask = labels == component
                    ys,xs = np.nonzero(mask)
                    body = None
                    if len(xs):
                        nonempty_masks += 1
                        x,y = int(xs.min()),int(ys.min())
                        right,bottom = int(xs.max())+1,int(ys.max())+1
                        body = NormalizedBox(x/frames.width,y/frames.height,
                            min((right-x)/frames.width,1-x/frames.width),
                            min((bottom-y)/frames.height,1-y/frames.height))
                    timestamp = round(i*frames.fps/frames.sample_fps)/frames.fps
                    if identity_samples is not None:
                        # Sampling rounds differently by at most one source frame.
                        # Require temporal agreement; never fuse stale detections.
                        identity_box = None
                        if i < len(identity_samples):
                            observed_at, candidate = identity_samples[i]
                            if abs(observed_at-timestamp) <= 1.01/frames.fps:
                                identity_box = candidate
                                if observed_at in trajectory_inferred_times:
                                    inferred_times.add(timestamp)
                        if continuity is not None:
                            body, inferred = continuity.update(timestamp, body, identity_box)
                            if inferred:
                                inferred_times.add(timestamp)
                                mask_inferred_count += 1
                        else:
                            body = validated_body_box(body, identity_box)
                    samples.append((timestamp,body))
                    # Forward-only use: keep a conservative 32-frame memory
                    # window and all conditioning frames. No backward replay.
                    for outputs in [state['output_dict'],*state['output_dict_per_obj'].values()]:
                        old = outputs['non_cond_frame_outputs']
                        for key in list(old):
                            if key < i-32:
                                del old[key]
                    if i % 25 == 0:
                        print(json.dumps({'phase':'mask_tracking','frames':i+1,'total':len(frames)}),flush=True)
            rendered = render_preview(args.source,args.output,tuple(samples),
                duration=args.duration,member_code=args.member,
                inferred_times=inferred_times,
                missing_policy='hold' if args.offline_trajectories else 'bridge',
                hold_seconds=args.absence_hold_seconds)
        print(json.dumps({'validationStatus':('fusion_unvalidated' if args.identity_fusion
                                              else 'mask_only_unvalidated'),
            'identity':identity_report,
            'sampleCount':len(samples),'nonemptyMasks':nonempty_masks,
            'maskInferredSamples':mask_inferred_count,
            'trajectoryInferredSamples':len(trajectory_inferred_times),
            'maskReseeds':reseed_count,
            'acceptedGeometrySamples':sum(b is not None for _,b in samples),
            'maxGeometryWidth':max((b.width for _,b in samples if b is not None),default=0),
            'maxGeometryHeight':max((b.height for _,b in samples if b is not None),default=0),
            'elapsedSeconds':round(time.perf_counter()-start,2),'render':rendered}))
    finally:
        frames.close()


if __name__ == '__main__':
    main()
