from __future__ import annotations

import json
from pathlib import Path

from stage_lab_analysis.candidates import Candidate, CandidateSet
from stage_lab_analysis.detection import NormalizedBox
from stage_lab_analysis.identity import (
    ConservativeIdentityClusterer,
    IdentityDecision,
    IdentityCluster,
    IdentityClusteringResult,
    TrackDescriptor,
    TrackFragment,
)
from stage_lab_analysis.tracking import Track, TrackSample
from stage_lab_analysis.worker import AnalysisWorker


def fragment(
    track_id: int,
    *,
    start: float,
    end: float,
    histogram: tuple[float, ...],
    edge_density: float = 0.2,
    center_x: float = 0.5,
    velocity_x: float = 0.0,
) -> TrackFragment:
    track = Track(
        track_id=track_id,
        samples=[
            TrackSample(start, NormalizedBox(center_x - 0.1, 0.1, 0.2, 0.7), 0.9),
            TrackSample(end, NormalizedBox(center_x - 0.1, 0.1, 0.2, 0.7), 0.9),
        ],
    )
    return TrackFragment(
        fragment_id=track_id,
        track=track,
        descriptor=TrackDescriptor(
            hsv_histogram=histogram,
            edge_density=edge_density,
            shoulder_to_hip_ratio=None,
            torso_to_height_ratio=None,
            pose_quality=0.0,
            start_center=(center_x, 0.45),
            end_center=(center_x, 0.45),
            velocity=(velocity_x, 0.0),
        ),
    )


def test_high_confidence_adjacent_fragments_merge_into_one_cluster() -> None:
    first = fragment(1, start=0, end=2, histogram=(0.2, 0.3, 0.5))
    second = fragment(2, start=2.2, end=4, histogram=(0.2, 0.3, 0.5))

    result = ConservativeIdentityClusterer().cluster((second, first))

    assert len(result.clusters) == 1
    assert result.clusters[0].fragment_ids == (1, 2)
    assert result.decisions == (IdentityDecision.merge(1, 2),)


def test_visually_different_fragments_are_not_merged() -> None:
    first = fragment(1, start=0, end=2, histogram=(1.0, 0.0, 0.0), edge_density=0.1)
    second = fragment(2, start=2.2, end=4, histogram=(0.0, 0.0, 1.0), edge_density=0.9)

    result = ConservativeIdentityClusterer().cluster((first, second))

    assert [cluster.fragment_ids for cluster in result.clusters] == [(1,), (2,)]
    assert result.decisions[0].kind is IdentityDecision.reject(1, 2).kind


def test_confirmation_band_never_merges_ambiguous_fragments() -> None:
    first = fragment(1, start=0, end=2, histogram=(0.2, 0.3, 0.5), edge_density=0.2)
    second = fragment(2, start=2.2, end=4, histogram=(0.6, 0.2, 0.2), edge_density=0.2)

    result = ConservativeIdentityClusterer().cluster((first, second))

    assert [cluster.fragment_ids for cluster in result.clusters] == [(1,), (2,)]
    assert result.decisions[0].kind is IdentityDecision.awaiting_confirmation(1, 2).kind


def test_missing_pose_requires_the_stricter_automatic_merge_threshold() -> None:
    first = fragment(1, start=0, end=2, histogram=(1.0, 0.0, 0.0), edge_density=0.2)
    second = fragment(2, start=2.2, end=4, histogram=(0.8, 0.2, 0.0), edge_density=0.2)

    result = ConservativeIdentityClusterer().cluster((first, second))

    assert result.decisions[0].kind is IdentityDecision.awaiting_confirmation(1, 2).kind


def test_impossible_travel_is_rejected_before_identity_scoring() -> None:
    first = fragment(1, start=0, end=2, histogram=(0.2, 0.3, 0.5), center_x=0.2)
    second = fragment(2, start=2.2, end=4, histogram=(0.2, 0.3, 0.5), center_x=0.9)

    result = ConservativeIdentityClusterer().cluster((first, second))

    assert result.decisions == (IdentityDecision.reject(1, 2),)


def test_overlapping_or_invalid_fragments_are_rejected_without_a_guess() -> None:
    first = fragment(1, start=0, end=2, histogram=(0.2, 0.3, 0.5))
    overlapping = fragment(2, start=1.9, end=4, histogram=(0.2, 0.3, 0.5))
    invalid = fragment(3, start=4.2, end=6, histogram=(float("nan"),))

    result = ConservativeIdentityClusterer().cluster((first, overlapping, invalid))

    assert [cluster.fragment_ids for cluster in result.clusters] == [(1,), (2,), (3,)]
    assert [decision.kind for decision in result.decisions] == [
        IdentityDecision.reject(1, 2).kind,
        IdentityDecision.reject(2, 3).kind,
    ]


def test_cluster_output_is_deterministic_when_input_order_changes() -> None:
    first = fragment(1, start=0, end=2, histogram=(0.2, 0.3, 0.5))
    second = fragment(2, start=2.2, end=4, histogram=(0.2, 0.3, 0.5))

    ordered = ConservativeIdentityClusterer().cluster((first, second))
    reordered = ConservativeIdentityClusterer().cluster((second, first))

    assert ordered == reordered


def test_descriptor_allows_negative_velocity_for_leftward_motion() -> None:
    descriptor = TrackDescriptor(
        hsv_histogram=(0.2, 0.3, 0.5),
        edge_density=0.2,
        shoulder_to_hip_ratio=None,
        torso_to_height_ratio=None,
        pose_quality=0,
        start_center=(0.6, 0.4),
        end_center=(0.4, 0.4),
        velocity=(-0.1, 0.0),
    )

    assert descriptor.is_valid


def test_identity_artifact_uses_strict_json_for_invalid_descriptors(tmp_path: Path) -> None:
    invalid = fragment(1, start=0, end=2, histogram=(float("nan"),))
    candidate = Candidate(
        candidate_id="candidate-1",
        fragment_ids=(1,),
        representative_image_paths=("first.jpg", "second.jpg", "third.jpg"),
        appearance_intervals=((0.0, 2.0),),
        box_summary=invalid.track.samples[0].box,
        confidence=0.9,
    )

    AnalysisWorker._write_identity_clusters(
        tmp_path,
        IdentityClusteringResult((IdentityCluster(1, (invalid,)),), ()),
        CandidateSet((candidate,)),
    )

    payload = json.loads((tmp_path / "identity-clusters.json").read_text())
    descriptor = payload["fragments"][0]["descriptor"]
    assert descriptor["valid"] is False
    assert descriptor["hsvHistogram"] == [None]
