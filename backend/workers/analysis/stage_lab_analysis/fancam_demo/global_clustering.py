from __future__ import annotations

import itertools
import math

from ..reid import PersonEmbedding, cosine_similarity


FIXED_MEMBER_COUNT = 5
_MAX_CONVERGENCE_ITERATIONS = 50


class _CandidateRejected(ValueError):
    """A seed-specific failure that must not reject otherwise valid seeds."""


def cluster_fixed_group_member_ids(
    scene_embeddings: tuple[tuple[PersonEmbedding, ...], ...],
    *,
    member_count: int = FIXED_MEMBER_COUNT,
) -> tuple[tuple[str, ...], ...]:
    """Assign stable anonymous member IDs with scene-level cannot-link constraints."""
    if not scene_embeddings:
        raise ValueError("at least one scene is required")
    if any(not scene for scene in scene_embeddings):
        raise ValueError("scene embeddings must not be empty")
    if member_count != FIXED_MEMBER_COUNT:
        raise ValueError(f"member_count must be {FIXED_MEMBER_COUNT}")
    if any(len(scene) > member_count for scene in scene_embeddings):
        raise ValueError(f"scenes must contain at most {member_count} detections")
    if sum(len(scene) for scene in scene_embeddings) < member_count:
        raise ValueError(f"at least {member_count} detections are required")
    dimensions = {
        len(embedding.values)
        for scene in scene_embeddings
        for embedding in scene
    }
    if len(dimensions) != 1:
        raise ValueError("embedding dimensions must match")

    seed_indices = [
        scene_index
        for scene_index, scene in enumerate(scene_embeddings)
        if len(scene) == member_count
    ]
    if not seed_indices:
        raise ValueError("at least one complete seed scene is required")

    candidates = []
    for seed_index in seed_indices:
        try:
            converged = _converge_candidate(
                scene_embeddings, scene_embeddings[seed_index], member_count
            )
        except _CandidateRejected:
            continue
        if converged is None:
            continue
        assignments, centroids = converged
        candidates.append(
            (_objective_score(scene_embeddings, assignments, centroids), seed_index, assignments)
        )
    if not candidates:
        raise ValueError("no candidate converged")

    _, _, winner = min(
        candidates, key=lambda candidate: (-candidate[0], candidate[1], candidate[2])
    )
    return tuple(
        tuple(f"member-{member_index + 1:02d}" for member_index in scene)
        for scene in winner
    )


def _best_scene_permutation(
    scene: tuple[PersonEmbedding, ...],
    centroids: tuple[PersonEmbedding, ...],
) -> tuple[int, ...]:
    scored = (
        (
            sum(
                cosine_similarity(embedding, centroids[member_index])
                for embedding, member_index in zip(scene, permutation)
            ),
            permutation,
        )
        for permutation in itertools.permutations(range(len(centroids)), len(scene))
    )
    return min(scored, key=lambda item: (-item[0], item[1]))[1]


def _recompute_normalized_centroids(
    scene_embeddings: tuple[tuple[PersonEmbedding, ...], ...],
    assignments: tuple[tuple[int, ...], ...],
    member_count: int,
) -> tuple[PersonEmbedding, ...]:
    assigned: list[list[PersonEmbedding]] = [[] for _ in range(member_count)]
    for scene, scene_assignment in zip(scene_embeddings, assignments):
        for embedding, member_index in zip(scene, scene_assignment):
            assigned[member_index].append(embedding)

    centroids = []
    for member_embeddings in assigned:
        if not member_embeddings:
            raise _CandidateRejected("cannot compute centroid for an empty member")
        dimension = len(member_embeddings[0].values)
        if any(len(embedding.values) != dimension for embedding in member_embeddings):
            raise ValueError("embedding dimensions must match")
        mean = tuple(
            sum(embedding.values[index] for embedding in member_embeddings)
            / len(member_embeddings)
            for index in range(dimension)
        )
        norm = math.sqrt(sum(value * value for value in mean))
        if norm == 0.0:
            raise _CandidateRejected("centroid norm must be non-zero")
        quality = sum(embedding.quality for embedding in member_embeddings) / len(
            member_embeddings
        )
        centroids.append(PersonEmbedding(tuple(value / norm for value in mean), quality))
    return tuple(centroids)


def _converge_candidate(
    scene_embeddings: tuple[tuple[PersonEmbedding, ...], ...],
    seed_centroids: tuple[PersonEmbedding, ...],
    member_count: int,
) -> tuple[tuple[tuple[int, ...], ...], tuple[PersonEmbedding, ...]] | None:
    centroids = seed_centroids
    previous_assignments = None
    for _ in range(_MAX_CONVERGENCE_ITERATIONS):
        assignments = tuple(
            _best_scene_permutation(scene, centroids) for scene in scene_embeddings
        )
        centroids = _recompute_normalized_centroids(
            scene_embeddings, assignments, member_count
        )
        if assignments == previous_assignments:
            return assignments, centroids
        previous_assignments = assignments
    return None


def _objective_score(
    scene_embeddings: tuple[tuple[PersonEmbedding, ...], ...],
    assignments: tuple[tuple[int, ...], ...],
    centroids: tuple[PersonEmbedding, ...],
) -> float:
    return sum(
        cosine_similarity(embedding, centroids[member_index])
        for scene, scene_assignment in zip(scene_embeddings, assignments)
        for embedding, member_index in zip(scene, scene_assignment)
    )
