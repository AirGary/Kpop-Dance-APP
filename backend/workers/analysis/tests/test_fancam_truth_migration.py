from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from stage_lab_analysis.detection import Detection, NormalizedBox
from stage_lab_analysis.fancam_demo import truth_migration
from stage_lab_analysis.fancam_demo import truth_migration_cli as cli
from stage_lab_analysis.fancam_demo.local_review import LegacyTruthReviewSession
from stage_lab_analysis.fancam_demo.truth_migration import LegacyTruthScene, migrate_legacy_truth
from stage_lab_analysis.reid import PersonEmbedding


def _basis_embedding(index: int) -> PersonEmbedding:
    return PersonEmbedding(
        tuple(1.0 if dimension == index else 0.0 for dimension in range(5)),
        1.0,
    )


def _write_legacy_truth(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "scenes": [
                    {
                        "timestampSeconds": float(timestamp),
                        "visibleMemberIds": ["candidate-01"],
                    }
                    for timestamp in range(30)
                ],
            }
        ),
        encoding="utf-8",
    )


def _valid_30_scenes_with_first_two(
    *first_two: LegacyTruthScene,
) -> tuple[LegacyTruthScene, ...]:
    return tuple(first_two) + tuple(
        LegacyTruthScene(float(index), (f"candidate-{index:02d}",))
        for index in range(3, 31)
    )


class StaticDetector:
    def __init__(self, *detections_per_frame: tuple[Detection, ...]) -> None:
        self._detections_per_frame = iter(detections_per_frame)

    def detect(self, frame: object) -> tuple[Detection, ...]:
        del frame
        return next(self._detections_per_frame)


class StaticEmbedder:
    def __init__(self, *embeddings: PersonEmbedding | None) -> None:
        self._embeddings = iter(embeddings)

    def embed(self, frame: object, box: NormalizedBox) -> PersonEmbedding | None:
        del frame, box
        return next(self._embeddings)


class RecordingEmbedder:
    def __init__(self, *embeddings: PersonEmbedding | None) -> None:
        self._embeddings = iter(embeddings)
        self.boxes: list[NormalizedBox] = []

    def embed(self, frame: object, box: NormalizedBox) -> PersonEmbedding | None:
        del frame
        self.boxes.append(box)
        return next(self._embeddings)


class BoxAwareEmbedder:
    def __init__(self, recovered_box: NormalizedBox) -> None:
        self._recovered_box = recovered_box
        self.boxes: list[NormalizedBox] = []

    def embed(self, frame: object, box: NormalizedBox) -> PersonEmbedding | None:
        del frame
        self.boxes.append(box)
        return PersonEmbedding((1.0, 0.0), 1.0) if box == self._recovered_box else None


def test_collect_assignments_clusters_fixed_group_without_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    complete_scene = tuple(
        Detection(0.0, NormalizedBox(index * 0.18, 0.0, 0.15, 0.8), 0.9)
        for index in range(5)
    )
    tail = Detection(2.0, NormalizedBox(0.2, 0.0, 0.3, 0.8), 0.9)
    monkeypatch.setattr(cli, "_read_frame", lambda source, timestamp: object())

    assignments = cli.collect_complete_assignments(
        Path("source"),
        _valid_30_scenes_with_first_two(
            LegacyTruthScene(
                0.0,
                tuple(f"candidate-{index:02d}" for index in range(1, 6)),
            ),
            LegacyTruthScene(1.0, ("candidate-06",)),
        ),
        StaticDetector(complete_scene, (tail,), *((tail,) for _ in range(28))),
        StaticEmbedder(
            *(_basis_embedding(index) for index in range(5)),
            *(_basis_embedding(0) for _ in range(29)),
        ),
    )

    assert all(
        len(scene_member_ids) == len(set(scene_member_ids))
        for scene_member_ids in assignments.scene_member_ids
    )


@pytest.mark.parametrize("embedding", [None])
def test_collect_assignments_rejects_missing_embedding(
    monkeypatch: pytest.MonkeyPatch, embedding: PersonEmbedding | None
) -> None:
    detection = Detection(0.0, NormalizedBox(0.2, 0.1, 0.3, 0.7), 0.9)
    monkeypatch.setattr(cli, "_read_frame", lambda source, timestamp: object())

    with pytest.raises(cli.MigrationRejected):
        cli.collect_complete_assignments(
        Path("source"),
        (LegacyTruthScene(0.0, ("candidate-01",)),),
        StaticDetector((detection,), ()),
        StaticEmbedder(embedding, None),
        )


def test_collect_assignments_retries_expanded_box_with_same_embedder_when_primary_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    detection = Detection(0.0, NormalizedBox(0.20, 0.20, 0.40, 0.40), 0.9)
    monkeypatch.setattr(cli, "_read_frame", lambda source, timestamp: object())
    monkeypatch.setattr(cli, "cluster_fixed_group_member_ids", lambda _: (("member-01",),))
    embedder = RecordingEmbedder(None, PersonEmbedding((1.0, 0.0), 1.0))

    assignments = cli.collect_complete_assignments(
        Path("source"),
        (LegacyTruthScene(0.0, ("candidate-01",)),),
        StaticDetector((detection,)),
        embedder,
    )

    assert assignments.scene_member_ids == (("member-01",),)
    assert embedder.boxes[0] == detection.box
    assert embedder.boxes[1].x == pytest.approx(0.10)
    assert embedder.boxes[1].y == pytest.approx(0.10)
    assert embedder.boxes[1].width == pytest.approx(0.60)
    assert embedder.boxes[1].height == pytest.approx(0.60)


def test_collect_assignments_recovers_missing_primary_embedding_from_tracked_nearby_detection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    anchor = Detection(0.0, NormalizedBox(0.20, 0.20, 0.30, 0.50), 0.9)
    unrelated = Detection(0.25, NormalizedBox(0.65, 0.15, 0.25, 0.50), 0.9)
    tracked = Detection(0.25, NormalizedBox(0.22, 0.20, 0.30, 0.50), 0.9)
    read_timestamps: list[float] = []

    def read_frame(source: Path, timestamp: float) -> object:
        del source
        read_timestamps.append(timestamp)
        return object()

    monkeypatch.setattr(cli, "_read_frame", read_frame)
    monkeypatch.setattr(cli, "cluster_fixed_group_member_ids", lambda _: (("member-01",),))
    embedder = BoxAwareEmbedder(tracked.box)

    assignments = cli.collect_complete_assignments(
        Path("source"),
        (LegacyTruthScene(0.0, ("candidate-01",)),),
        StaticDetector((anchor,), (unrelated, tracked)),
        embedder,
    )

    assert assignments.scene_member_ids == (("member-01",),)
    assert read_timestamps == [0.0, 0.25]
    assert embedder.boxes == [anchor.box, cli.expanded_retry_box(anchor.box), tracked.box]


def test_collect_assignments_does_not_retry_for_valid_primary_embedding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    detection = Detection(0.0, NormalizedBox(0.0, 0.0, 1.0, 1.0), 0.9)
    monkeypatch.setattr(cli, "_read_frame", lambda source, timestamp: object())
    monkeypatch.setattr(cli, "cluster_fixed_group_member_ids", lambda _: (("member-01",),))
    embedder = RecordingEmbedder(PersonEmbedding((1.0, 0.0), 1.0))

    assignments = cli.collect_complete_assignments(
        Path("source"),
        (LegacyTruthScene(0.0, ("candidate-01",)),),
        StaticDetector((detection,)),
        embedder,
    )

    assert assignments.scene_member_ids == (("member-01",),)
    assert embedder.boxes == [detection.box]


def test_collect_assignments_clusters_primary_and_retry_embeddings_together(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    complete_scene = tuple(
        Detection(0.0, NormalizedBox(index * 0.18, 0.0, 0.15, 0.8), 0.9)
        for index in range(5)
    )
    tail = Detection(1.0, NormalizedBox(0.2, 0.0, 0.3, 0.8), 0.9)
    monkeypatch.setattr(cli, "_read_frame", lambda source, timestamp: object())

    assignments = cli.collect_complete_assignments(
        Path("source"),
        _valid_30_scenes_with_first_two(
            LegacyTruthScene(
                0.0,
                tuple(f"candidate-{index:02d}" for index in range(1, 6)),
            ),
            LegacyTruthScene(1.0, ("candidate-06",)),
        ),
        StaticDetector(complete_scene, (tail,), *((tail,) for _ in range(28))),
        RecordingEmbedder(
            _basis_embedding(0),
            _basis_embedding(1),
            None,
            _basis_embedding(2),
            _basis_embedding(3),
            _basis_embedding(4),
            *(_basis_embedding(0) for _ in range(29)),
        ),
    )

    assert all(
        len(scene_member_ids) == len(set(scene_member_ids))
        for scene_member_ids in assignments.scene_member_ids
    )


def test_collect_assignments_rejects_detection_count_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scene = LegacyTruthScene(0.0, ("candidate-01", "candidate-02"))
    detection = Detection(0.0, NormalizedBox(0.0, 0.0, 0.4, 0.8), 0.9)
    monkeypatch.setattr(cli, "_read_frame", lambda source, timestamp: object())

    with pytest.raises(cli.MigrationRejected):
        cli.collect_complete_assignments(
            Path("source"),
            (scene,),
            StaticDetector((detection,)),
            StaticEmbedder(PersonEmbedding((1.0, 0.0), 1.0)),
        )


def test_collect_assignments_keeps_only_five_highest_confidence_detections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    detections = tuple(
        Detection(
            0.0,
            NormalizedBox(index / 10.0, 0.0, 0.05, 0.8),
            confidence,
        )
        for index, confidence in enumerate((0.30, 0.99, 0.98, 0.97, 0.96, 0.95))
    )
    legacy_scene = LegacyTruthScene(
        0.0,
        tuple(f"candidate-{index:02d}" for index in range(1, 7)),
    )
    monkeypatch.setattr(cli, "_read_frame", lambda source, timestamp: object())

    collected = cli.collect_complete_assignments(
        Path("source"),
        (legacy_scene,),
        StaticDetector(detections),
        StaticEmbedder(*(PersonEmbedding((1.0, 0.0), 1.0) for _ in range(5))),
    )

    assert collected.legacy_scenes == (
        LegacyTruthScene(
            0.0,
            ("candidate-02", "candidate-03", "candidate-04", "candidate-05", "candidate-06"),
        ),
    )
    assert collected.scene_member_ids == (("member-01", "member-02", "member-03", "member-04", "member-05"),)


def test_migration_preserves_legacy_backup_and_creates_stable_canonical(
    tmp_path: Path,
) -> None:
    legacy = tmp_path / "legacy-truth.json"
    backup = tmp_path / "fancam-demo-ground-truth.legacy.local.json"
    destination = tmp_path / "fancam-demo-ground-truth.local.json"
    _write_legacy_truth(legacy)
    truth = truth_migration.convert_scene_member_ids(
        truth_migration.load_legacy_truth(legacy),
        tuple(("member-01",) for _ in range(30)),
    )

    migrated = migrate_legacy_truth(legacy, backup, destination, truth)

    assert migrated.scenes[0].visible_member_ids == ("member-01",)
    assert backup.exists() and destination.exists()


def test_migration_refuses_existing_backup_without_changing_legacy(
    tmp_path: Path,
) -> None:
    legacy = tmp_path / "legacy-truth.json"
    backup = tmp_path / "fancam-demo-ground-truth.legacy.local.json"
    destination = tmp_path / "fancam-demo-ground-truth.local.json"
    _write_legacy_truth(legacy)
    legacy_payload = legacy.read_bytes()
    backup.write_text("existing backup", encoding="utf-8")
    truth = truth_migration.convert_scene_member_ids(
        truth_migration.load_legacy_truth(legacy),
        tuple(("member-01",) for _ in range(30)),
    )

    with pytest.raises(FileExistsError):
        migrate_legacy_truth(legacy, backup, destination, truth)

    assert legacy.read_bytes() == legacy_payload
    assert backup.read_text(encoding="utf-8") == "existing backup"
    assert not destination.exists()


def test_migration_restores_legacy_after_publication_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    legacy = tmp_path / "legacy-truth.json"
    backup = tmp_path / "fancam-demo-ground-truth.legacy.local.json"
    destination = tmp_path / "fancam-demo-ground-truth.local.json"
    _write_legacy_truth(legacy)
    legacy_payload = legacy.read_bytes()
    truth = truth_migration.convert_scene_member_ids(
        truth_migration.load_legacy_truth(legacy),
        tuple(("member-01",) for _ in range(30)),
    )

    monkeypatch.setattr(
        truth_migration,
        "write_stable_truth_exclusive",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("synthetic failure")),
    )

    with pytest.raises(OSError, match="synthetic failure"):
        migrate_legacy_truth(legacy, backup, destination, truth)

    assert legacy.read_bytes() == legacy_payload
    assert not backup.exists() and not destination.exists()


def test_legacy_truth_reviewer_prompts_again_for_same_candidate_id() -> None:
    class Reviewer(LegacyTruthReviewSession):
        def __init__(self) -> None:
            super().__init__()
            self.prompt_calls = 0

        def _prompt(self, frame: object, detection: object, candidate_id: str) -> str | None:
            del frame, detection, candidate_id
            self.prompt_calls += 1
            return chr(ord("A") + self.prompt_calls - 1)

    reviewer = Reviewer()

    assert reviewer.review_candidate(object(), object(), "candidate-01") == "A"
    assert reviewer.review_candidate(object(), object(), "candidate-01") == "B"
    assert reviewer.prompt_calls == 2


def test_legacy_truth_review_displays_source_context_and_detection_box(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import numpy as np

    displayed_text: list[str] = []
    displayed_images: list[np.ndarray] = []
    rectangles: list[tuple[tuple[int, int], tuple[int, int], int]] = []

    class _OpenCV:
        FONT_HERSHEY_SIMPLEX = 0
        LINE_AA = 0

        @staticmethod
        def putText(image, text, *args):
            displayed_text.append(text)

        @staticmethod
        def rectangle(image, pt1, pt2, color, thickness):
            rectangles.append((pt1, pt2, thickness))

        @staticmethod
        def imshow(name, image):
            displayed_images.append(image.copy())

        @staticmethod
        def waitKey(delay):
            return ord("x")

        @staticmethod
        def destroyWindow(name):
            return None

    monkeypatch.setitem(sys.modules, "cv2", _OpenCV)
    reviewer = LegacyTruthReviewSession()

    assert reviewer.review_candidate(
        np.zeros((12, 20, 3), dtype=np.uint8),
        SimpleNamespace(box=SimpleNamespace(x=0.2, y=0.25, width=0.3, height=0.5)),
        "candidate-01",
    ) is None

    assert rectangles == [((4, 3), (10, 9), 2)]
    assert displayed_images and displayed_images[0].shape[1] > 20
    assert "candidate-01" not in displayed_text


def test_migration_cli_loads_components_and_writes_only_scene_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    legacy = tmp_path / "legacy-truth.json"
    backup = tmp_path / "fancam-demo-ground-truth.legacy.local.json"
    canonical = tmp_path / "fancam-demo-ground-truth.local.json"
    _write_legacy_truth(legacy)
    detector = object()
    embedder = object()
    monkeypatch.setattr(
        cli,
        "_arguments",
        lambda: SimpleNamespace(source=tmp_path / "source", model_root=tmp_path / "models"),
    )
    monkeypatch.setattr(cli, "_legacy_path", lambda: legacy)
    monkeypatch.setattr(cli, "_backup_path", lambda: backup)
    monkeypatch.setattr(cli, "_canonical_path", lambda: canonical)
    monkeypatch.setattr(cli, "_components", lambda root: (detector, embedder))

    def collect_assignments(
        source: Path,
        legacy_scenes: tuple[LegacyTruthScene, ...],
        actual_detector: object,
        actual_embedder: object,
    ) -> cli.CollectedMigrationAssignments:
        assert source == tmp_path / "source"
        assert actual_detector is detector and actual_embedder is embedder
        return cli.CollectedMigrationAssignments(
            legacy_scenes,
            tuple(("member-01",) for _ in legacy_scenes),
        )

    monkeypatch.setattr(cli, "collect_complete_assignments", collect_assignments)

    cli.main()

    assert json.loads(capsys.readouterr().out) == {"migratedSceneCount": 30}
    assert backup.exists() and canonical.exists() and not legacy.exists()


def test_rejected_migration_keeps_legacy_and_prints_no_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    legacy = tmp_path / "legacy-truth.json"
    backup = tmp_path / "fancam-demo-ground-truth.legacy.local.json"
    canonical = tmp_path / "fancam-demo-ground-truth.local.json"
    _write_legacy_truth(legacy)
    monkeypatch.setattr(
        cli,
        "_arguments",
        lambda: SimpleNamespace(source=tmp_path / "source", model_root=tmp_path / "models"),
    )
    monkeypatch.setattr(cli, "_legacy_path", lambda: legacy)
    monkeypatch.setattr(cli, "_backup_path", lambda: backup)
    monkeypatch.setattr(cli, "_canonical_path", lambda: canonical)
    monkeypatch.setattr(
        cli,
        "collect_complete_assignments",
        lambda *_args: (_ for _ in ()).throw(cli.MigrationRejected()),
    )
    monkeypatch.setattr(cli, "_components", lambda root: (object(), object()))

    with pytest.raises(SystemExit) as exited:
        cli.main()

    assert exited.value.code != 0
    assert capsys.readouterr().out == ""
    assert legacy.exists() and not backup.exists() and not canonical.exists()
