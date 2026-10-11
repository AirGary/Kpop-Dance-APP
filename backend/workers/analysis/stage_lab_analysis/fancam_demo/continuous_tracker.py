"""Source-configured, runtime-only motion/appearance tracking for preview runs.

Association confidence is a heuristic, not a measured identity accuracy.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math

import numpy as np
from scipy.optimize import linear_sum_assignment

from ..detection import Detection, NormalizedBox
from ..reid import PersonEmbedding, cosine_similarity, MIN_REID_EMBEDDING_QUALITY


@dataclass
class _Track:
    box: NormalizedBox
    timestamp: float
    velocity: tuple[float, float] = (0., 0.)
    gallery: list[PersonEmbedding] = field(default_factory=list)
    reentry_box: NormalizedBox | None = None
    reentry_timestamp: float = -1.
    reentry_streak: int = 0
    motion_box: NormalizedBox | None = None
    motion_timestamp: float = -1.
    uncertain: bool = False
    pending_reseed: bool = False
    confirmation_box: NormalizedBox | None = None
    confirmation_embedding: PersonEmbedding | None = None
    confirmation_time: float = -1.
    confirmation_count: int = 0

    def predict(self, timestamp: float) -> NormalizedBox:
        if self.motion_box is not None and timestamp-self.motion_timestamp <= .5:
            return self.motion_box
        dt = min(timestamp - self.timestamp, .5)
        x = min(1-self.box.width, max(0., self.box.x+self.velocity[0]*dt))
        y = min(1-self.box.height, max(0., self.box.y+self.velocity[1]*dt))
        return NormalizedBox(x, y, self.box.width, self.box.height)


class ContinuousMemberTracker:
    """Initialize member indices left-to-right once; never create extra identities."""

    _IMMEDIATE_REENTRY_SIMILARITY = .9
    _IMMEDIATE_REENTRY_LEAD = .08
    _RELAXED_REENTRY_SIMILARITY = .65
    _RELAXED_REENTRY_LEAD = .20
    _RELAXED_REENTRY_STREAK = 3

    def __init__(self, member_count: int, *, max_gap: float = 2., strict_reentry: bool = False,
                 separate_identity: bool = False) -> None:
        if isinstance(member_count, bool) or not isinstance(member_count, int) or not 1 <= member_count <= 20:
            raise ValueError("member_count must be between 1 and 20")
        if not math.isfinite(max_gap) or max_gap <= 0:
            raise ValueError("max_gap must be positive")
        self.member_count = member_count
        self.max_gap = max_gap
        self.strict_reentry = strict_reentry
        if separate_identity and not strict_reentry:
            raise ValueError('identity separation requires strict reentry')
        self.separate_identity = separate_identity
        self.reacquired: set[int] = set()
        self.tracks: list[_Track] = []
        self.last_timestamp = -1.

    def update(self, timestamp: float, detections: tuple[Detection, ...],
               embeddings: tuple[PersonEmbedding | None, ...]) -> dict[int, NormalizedBox]:
        if not math.isfinite(timestamp) or timestamp < 0 or timestamp <= self.last_timestamp:
            raise ValueError("timestamps must be finite, non-negative and increasing")
        if len(detections) != len(embeddings):
            raise ValueError("detections and embeddings must align")
        self.last_timestamp = timestamp
        self.reacquired = set()
        if not self.tracks:
            if len(detections) < self.member_count:
                return {}
            indices = sorted(range(len(detections)), key=lambda i: (-detections[i].confidence, i))[:self.member_count]
            indices.sort(key=lambda i: detections[i].box.x+detections[i].box.width/2)
            self.tracks = [_Track(detections[i].box, timestamp,
                gallery=[embeddings[i]] if self._safe_template(i, detections, embeddings[i]) else [])
                for i in indices]
            for track in self.tracks:
                track.uncertain = self.separate_identity and not track.gallery
            return {i: track.box for i, track in enumerate(self.tracks)
                    if not self.separate_identity or track.gallery}
        if not detections:
            for track in self.tracks:
                self._clear_reentry(track)
                if self.separate_identity:
                    track.uncertain = True
                    track.confirmation_count = 0
            return {}

        n, m = len(self.tracks), len(detections)
        long_reentry: dict[int, set[int]] = {}
        for i, track in enumerate(self.tracks):
            if timestamp-track.timestamp <= self.max_gap:
                self._clear_reentry(track)
                continue
            immediate: list[tuple[float, int]] = []
            relaxed: list[tuple[float, float, int]] = []
            for j, embedding in enumerate(embeddings):
                if embedding is None:
                    continue
                if self.strict_reentry and not self._safe_template(j, detections, embedding):
                    continue
                similarity = max((cosine_similarity(embedding, item)
                                  for item in track.gallery), default=None)
                if similarity is None:
                    continue
                other_best = max((cosine_similarity(embedding, item)
                                  for other in self.tracks if other is not track
                                  for item in other.gallery), default=-1.)
                lead = similarity-other_best
                if (similarity >= self._IMMEDIATE_REENTRY_SIMILARITY
                        and lead >= self._IMMEDIATE_REENTRY_LEAD):
                    immediate.append((similarity, j))
                if (similarity >= self._RELAXED_REENTRY_SIMILARITY
                        and lead >= self._RELAXED_REENTRY_LEAD) or (
                        self.strict_reentry and similarity >= self._IMMEDIATE_REENTRY_SIMILARITY
                        and lead >= self._IMMEDIATE_REENTRY_LEAD):
                    relaxed.append((similarity, lead, j))
            if immediate and not self.strict_reentry:
                long_reentry[i] = {j for _, j in immediate}
                self._clear_reentry(track)
                continue
            if not relaxed:
                self._clear_reentry(track)
                continue
            _, _, candidate_index = max(relaxed, key=lambda item: (item[0], item[1], -item[2]))
            candidate_box = detections[candidate_index].box
            if self._continues_reentry(track, candidate_box, timestamp):
                track.reentry_streak += 1
            else:
                track.reentry_streak = 1
            track.reentry_box = candidate_box
            track.reentry_timestamp = timestamp
            if track.reentry_streak >= self._RELAXED_REENTRY_STREAK:
                long_reentry[i] = {candidate_index}

        # Private dummy columns allow every member to remain unmatched.
        costs = np.full((n, m+n), 100., dtype=float)
        for i, track in enumerate(self.tracks):
            costs[i, m+i] = .95
            motion_time = (track.motion_timestamp if self.separate_identity
                           and track.motion_box is not None else track.timestamp)
            dt = timestamp-motion_time
            predicted = track.predict(timestamp)
            for j, (detection, embedding) in enumerate(zip(detections, embeddings)):
                box = detection.box
                dx = box.x+box.width/2-predicted.x-predicted.width/2
                dy = box.y+box.height/2-predicted.y-predicted.height/2
                distance = math.hypot(dx, dy)
                radius = min(.25, .04+.20*dt)
                similarity = max((cosine_similarity(embedding, e) for e in track.gallery), default=None) if embedding else None
                if (self.separate_identity and timestamp-track.timestamp > self.max_gap
                        and similarity is not None and j in long_reentry.get(i, ())):
                    costs[i, j] = 1-similarity
                    continue
                if dt > self.max_gap:
                    # Global re-entry never trusts stale motion. Exact appearance
                    # can return immediately; weaker but member-distinctive
                    # appearance must persist across three geometrically
                    # continuous observations before it may update trusted state.
                    if similarity is not None and j in long_reentry.get(i, ()):
                        costs[i, j] = 1-similarity
                    continue
                if distance > radius:
                    continue
                if similarity is not None and similarity < .35:
                    continue
                if self.strict_reentry and self._appearance_conflicts(track, embedding, similarity):
                    continue
                if dt > .6 and (similarity is None or similarity < .8):
                    continue
                if similarity is None and dt <= .6:
                    # Short motion-only matches must not replace a full body
                    # with an occluder's partial/merged box. The reciprocal
                    # 1.5 scale bound rejects observed 1.758/.594 height jumps
                    # while allowing modest detector jitter. It can reject
                    # genuine rapid pose/zoom changes; it is not an identity
                    # guarantee and must not gate appearance-based re-entry.
                    previous = track.motion_box or track.box
                    width_ratio = box.width/previous.width
                    height_ratio = box.height/previous.height
                    if not (1/1.5 <= width_ratio <= 1.5 and 1/1.5 <= height_ratio <= 1.5):
                        continue
                motion = .55*(1-predicted.iou(box)) + .45*min(1., distance/radius)
                costs[i, j] = motion if similarity is None else .6*motion+.4*(1-similarity)
        rows, cols = linear_sum_assignment(costs)
        best = float(costs[rows, cols].sum())
        accepted = []
        for i, j in zip(rows, cols):
            if j >= m or costs[i, j] >= .95:
                continue
            alternative = costs.copy()
            alternative[i, j] = 100.
            ar, ac = linear_sum_assignment(alternative)
            if float(alternative[ar, ac].sum())-best < .06:
                continue
            accepted.append((int(i), int(j)))
        # Evaluate against the same pre-update galleries for every member.
        # A motion match is not permission to learn another member's appearance.
        learnable = {i for i, j in accepted
                     if self._safe_template(j, detections, embeddings[j])
                     and (not self.strict_reentry
                          or self._template_identity_consistent(self.tracks[i], embeddings[j]))}
        trusted = {i for i, j in accepted if not self.separate_identity
                   or self._confirm_identity(self.tracks[i], j, timestamp, detections, embeddings)}
        result = {}
        for i, j in accepted:
            track = self.tracks[i]
            box, embedding = detections[j].box, embeddings[j]
            dt = timestamp-track.timestamp
            if self.separate_identity:
                track.motion_box, track.motion_timestamp = box, timestamp
                if i not in trusted:
                    continue
                if track.uncertain:
                    track.pending_reseed = True
                if track.pending_reseed and self._safe_template(j, detections, embedding):
                    self.reacquired.add(i)
                    track.pending_reseed = False
                track.uncertain = False
            vx, vy = (box.x-track.box.x)/dt, (box.y-track.box.y)/dt
            track.velocity = (0., 0.) if dt > self.max_gap else (.5*vx+.5*track.velocity[0], .5*vy+.5*track.velocity[1])
            track.box, track.timestamp = box, timestamp
            self._clear_reentry(track)
            if i in learnable:
                track.gallery.append(embedding)
                if len(track.gallery) > 12:
                    del track.gallery[1]
            result[i] = box
        if self.separate_identity:
            for i, track in enumerate(self.tracks):
                if i not in result:
                    track.uncertain = True
                if i not in {a for a, _ in accepted}:
                    track.confirmation_count = 0
        return result

    def _confirm_identity(self, track, index, timestamp, detections, embeddings):
        embedding = embeddings[index]
        # Crop overlap prevents learning/reseeding, not a distinctive observation
        # against an existing identity. Missing anchors still require a clean crop.
        if (embedding is None or embedding.quality < MIN_REID_EMBEDDING_QUALITY
                or detections[index].confidence < .7
                or (not track.gallery and not self._safe_template(index, detections, embedding))):
            track.confirmation_count = 0
            return False
        other = max((cosine_similarity(embedding, item)
                     for candidate in self.tracks if candidate is not track
                     for item in candidate.gallery), default=-1.)
        own = max((cosine_similarity(embedding, item) for item in track.gallery), default=None)
        distinctive = (other < self._RELAXED_REENTRY_SIMILARITY if own is None else
                       ((own >= self._RELAXED_REENTRY_SIMILARITY and own-other >= self._RELAXED_REENTRY_LEAD)
                        or (own >= self._IMMEDIATE_REENTRY_SIMILARITY and own-other >= self._IMMEDIATE_REENTRY_LEAD)))
        if not distinctive:
            track.confirmation_count = 0
            return False
        if own is not None and not track.uncertain:
            return True
        # The long-gap path has already required three consistent observations.
        if (own is not None and track.reentry_streak >= self._RELAXED_REENTRY_STREAK
                and detections[index].box == track.reentry_box):
            return True
        box = detections[index].box
        previous = track.confirmation_box
        consistent = (previous is not None and 0 < timestamp-track.confirmation_time <= .5
                      and previous.iou(box) >= .3
                      and track.confirmation_embedding is not None
                      and cosine_similarity(embedding, track.confirmation_embedding) >= .65)
        track.confirmation_count = track.confirmation_count+1 if consistent else 1
        track.confirmation_box, track.confirmation_time = box, timestamp
        track.confirmation_embedding = embedding
        return track.confirmation_count >= self._RELAXED_REENTRY_STREAK

    def _template_identity_consistent(self, track, embedding):
        if not track.gallery:
            return True
        own = max(cosine_similarity(embedding, item) for item in track.gallery)
        other = max((cosine_similarity(embedding, item)
                     for candidate in self.tracks if candidate is not track
                     for item in candidate.gallery), default=-1.)
        return own > other

    def _appearance_conflicts(self, track, embedding, similarity):
        if embedding is None or similarity is None:
            return False
        other_best = max((cosine_similarity(embedding, item)
                          for other in self.tracks if other is not track
                          for item in other.gallery), default=-1.)
        # Reuse the existing strong-appearance and distinctiveness contract.
        # Motion must not override an explicit competing identity, even before
        # the long-gap re-entry branch. Rejecting also prevents gallery poisoning.
        return ((other_best >= self._IMMEDIATE_REENTRY_SIMILARITY
                 and other_best-similarity >= self._IMMEDIATE_REENTRY_LEAD)
                or (other_best >= self._RELAXED_REENTRY_SIMILARITY
                    and other_best-similarity >= self._RELAXED_REENTRY_LEAD))

    @staticmethod
    def _safe_template(index, detections, embedding) -> bool:
        # Conservative crop contamination gate; not an identity probability.
        # quality is a focus score, not a calibrated probability. Share the
        # embedder's validity contract instead of rejecting every real crop.
        if (embedding is None or embedding.quality < MIN_REID_EMBEDDING_QUALITY
                or detections[index].confidence < .7):
            return False
        box = detections[index].box
        for j, other in enumerate(detections):
            if j == index:
                continue
            b = other.box
            overlap = (max(0., min(box.x+box.width, b.x+b.width)-max(box.x, b.x))
                       * max(0., min(box.y+box.height, b.y+b.height)-max(box.y, b.y)))
            if overlap / (box.width*box.height) > .2:
                return False
        return True

    @staticmethod
    def _clear_reentry(track: _Track) -> None:
        track.reentry_box = None
        track.reentry_timestamp = -1.
        track.reentry_streak = 0

    @staticmethod
    def _continues_reentry(track: _Track, box: NormalizedBox, timestamp: float) -> bool:
        previous = track.reentry_box
        if previous is None or not 0 < timestamp-track.reentry_timestamp <= .5:
            return False
        dx = box.x+box.width/2-previous.x-previous.width/2
        dy = box.y+box.height/2-previous.y-previous.height/2
        width_ratio = box.width/previous.width
        height_ratio = box.height/previous.height
        return (math.hypot(dx, dy) <= .15
                and 1/1.5 <= width_ratio <= 1.5
                and 1/1.5 <= height_ratio <= 1.5)
