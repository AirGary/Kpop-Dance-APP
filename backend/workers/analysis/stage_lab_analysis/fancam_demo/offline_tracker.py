"""Runtime-only, fixed-member trajectory stitching; not identity ground truth."""
from __future__ import annotations

import math

import numpy as np
from scipy.optimize import linear_sum_assignment

from ..detection import NormalizedBox
from ..reid import MIN_REID_EMBEDDING_QUALITY, cosine_similarity


def frame_camera_transform(previous, current, *, previous_boxes=(), current_boxes=()):
    """Estimate conservative background translation from small grayscale frames."""
    import cv2
    if previous.shape != current.shape or previous.ndim != 2 or not previous.size:
        raise ValueError('camera frames must be aligned grayscale images')
    old_hist = cv2.calcHist([previous], [0], None, [32], [0, 256])
    new_hist = cv2.calcHist([current], [0], None, [32], [0, 256])
    if cv2.compareHist(old_hist, new_hist, cv2.HISTCMP_CORREL) < .05:
        return False
    shift, response = cv2.phaseCorrelate(
        previous.astype(np.float32), current.astype(np.float32))
    if response < .05 or not all(math.isfinite(v) for v in shift):
        return None
    height, width = previous.shape
    offset_x, offset_y = shift[0] / width, shift[1] / height
    if abs(offset_x) > .35 or abs(offset_y) > .35:
        return None
    masks = []
    for boxes in (previous_boxes, current_boxes):
        mask = np.full(previous.shape, 255, np.uint8)
        for box in boxes:
            cv2.rectangle(mask, (int(box.x * width), int(box.y * height)),
                (math.ceil((box.x + box.width) * width),
                 math.ceil((box.y + box.height) * height)), 0, -1)
        masks.append(cv2.erode(mask, np.ones((3, 3), np.uint8)))
    transform = np.float32([[1, 0, shift[0]], [0, 1, shift[1]]])
    warped = cv2.warpAffine(previous.astype(np.float32), transform, (width, height))
    warped_mask = cv2.warpAffine(masks[0], transform, (width, height))
    valid = (masks[0] == 255) & (masks[1] == 255) & (warped_mask == 255)
    if np.count_nonzero(valid) < 64:
        return None
    current_float = current.astype(np.float32)
    shifted_error = np.mean(np.abs(warped[valid] - current_float[valid]))
    static_error = np.mean(np.abs(previous.astype(np.float32)[valid] - current_float[valid]))
    # shortcut: background photometric support validates translation, not zoom/rotation.
    return (1., offset_x, offset_y) if shifted_error < static_error else (1., 0., 0.)


def _project_box(box, camera):
    scale, offset_x, offset_y = camera
    center_x = scale * (box.x + box.width / 2) + offset_x
    center_y = scale * (box.y + box.height / 2) + offset_y
    width = min(1., box.width * scale)
    height = min(1., box.height * scale)
    return NormalizedBox(min(1 - width, max(0., center_x - width / 2)),
                         min(1 - height, max(0., center_y - height / 2)), width, height)


def _association_cost(old, old_embedding, predicted, detection, embedding, dt):
    box = detection.box
    if detection.confidence < .1:
        return 100.
    if not (1 / 1.5 <= box.width / old.width <= 1.5
            and 1 / 1.5 <= box.height / old.height <= 1.5):
        return 100.
    distance = math.hypot(box.x + box.width / 2 - predicted.x - predicted.width / 2,
                          box.y + box.height / 2 - predicted.y - predicted.height / 2)
    radius = min(.25, .04 + .20 * dt)
    overlap = predicted.iou(box)
    # Large close-up boxes can overlap despite a large center shift.
    if distance > radius and overlap == 0.:
        return 100.
    similarity = None
    if (embedding is not None and old_embedding is not None
            and min(embedding.quality, old_embedding.quality) >= MIN_REID_EMBEDDING_QUALITY):
        similarity = cosine_similarity(embedding, old_embedding)
        if similarity < .35:
            return 100.
    motion = .55 * (1 - overlap) + .45 * distance / radius
    cost = motion if similarity is None else .6 * motion + .4 * (1 - similarity)
    # Weak detections continue strong-started paths but lose to equally strong evidence.
    return cost + (.15 if detection.confidence < .35 else 0.)


def _directional_links(observations, camera_transforms, *, reverse=False,
                       reciprocal_history=None):
    """Associate anonymous endpoints without creating or learning identities."""
    active = {}  # endpoint -> previous node, for directional velocity
    links = set()
    rescued = set()
    indices = range(len(observations) - 1, -1, -1) if reverse else range(len(observations))
    prior_frame = None
    for frame_index in indices:
        timestamp, detections, embeddings = observations[frame_index]
        camera = None
        if prior_frame is not None:
            camera = camera_transforms[prior_frame if reverse else frame_index]
            if reverse and camera not in (None, False):
                scale, offset_x, offset_y = camera
                camera = (1 / scale, -offset_x / scale, -offset_y / scale)
        if camera is False:
            active.clear()
        active = {node: previous for node, previous in active.items()
                  if abs(timestamp - observations[node[0]][0]) <= .5 + 1e-9}
        endpoints = list(active)
        n, m = len(endpoints), len(detections)
        costs = np.full((n, m + n), 100.)
        for row, node in enumerate(endpoints):
            old_time, old_detections, old_embeddings = observations[node[0]]
            old = old_detections[node[1]].box
            old_embedding = old_embeddings[node[1]]
            dt = abs(timestamp - old_time)
            predicted = old
            previous = active[node]
            if camera and node[0] == prior_frame:
                predicted = _project_box(old, camera)
                previous = None  # Do not carry subject velocity through camera motion.
            elif previous is not None:
                prior_time, prior_detections, _ = observations[previous[0]]
                prior = prior_detections[previous[1]].box
                ratio = (timestamp - old_time) / (old_time - prior_time)
                x = min(1 - old.width, max(0., old.x + (old.x - prior.x) * ratio))
                y = min(1 - old.height, max(0., old.y + (old.y - prior.y) * ratio))
                predicted = NormalizedBox(x, y, old.width, old.height)
            costs[row, m + row] = .95
            for col, detection in enumerate(detections):
                costs[row, col] = _association_cost(
                    old, old_embedding, predicted, detection, embeddings[col], dt)
        direct = costs[:, :m].copy() if reciprocal_history else None
        # Reconnect stale endpoints only where adjacent-frame continuity is absent.
        recent = [row for row, node in enumerate(endpoints) if node[0] == prior_frame]
        stale = [row for row, node in enumerate(endpoints) if node[0] != prior_frame]
        for col in range(m):
            if any(costs[row, col] < .95 for row in recent):
                costs[stale, col] = 100.
        assisted = set()
        if reciprocal_history:
            for row in recent:
                node = endpoints[row]
                previous = active[node]
                if (previous is None or node in rescued or previous in rescued
                        or abs(previous[0] - node[0]) != 1
                        or abs(frame_index - node[0]) != 1
                        or np.any(direct[row] < .95)):
                    continue
                edge = (node, previous) if reverse else (previous, node)
                if edge not in reciprocal_history:
                    continue
                old_time, old_detections, old_embeddings = observations[previous[0]]
                dt = abs(timestamp - old_time)
                history_camera = camera_transforms[previous[0] if reverse else node[0]]
                if dt > .5 + 1e-9 or history_camera in (None, False) or camera in (None, False):
                    continue
                scale, dx, dy = history_camera
                if reverse:
                    scale, dx, dy = 1 / scale, -dx / scale, -dy / scale
                next_scale, next_dx, next_dy = camera
                # Compose before clamping so offscreen intermediate geometry is retained.
                composed = (next_scale * scale, next_scale * dx + next_dx,
                            next_scale * dy + next_dy)
                old = old_detections[previous[1]].box
                predicted = _project_box(old, composed)
                for col, detection in enumerate(detections):
                    if direct[row, col] >= 100. or np.any(direct[:, col] < .95):
                        continue
                    cost = _association_cost(old, old_embeddings[previous[1]], predicted,
                                             detection, embeddings[col], dt)
                    if cost < .95:
                        costs[row, col] = cost
                        assisted.add((row, col))
        matched = {}
        if n:
            rows, cols = linear_sum_assignment(costs)
            best = float(costs[rows, cols].sum())
            for row, col in zip(rows, cols):
                if col >= m or costs[row, col] >= .95:
                    continue
                alternative = costs.copy()
                alternative[row, col] = 100.
                ar, ac = linear_sum_assignment(alternative)
                if float(alternative[ar, ac].sum()) - best < .06:
                    continue
                old_node, new_node = endpoints[row], (frame_index, int(col))
                links.add((new_node, old_node) if reverse else (old_node, new_node))
                if (row, col) in assisted:
                    rescued.add(new_node)
                matched[int(col)] = old_node
                del active[old_node]
        for col in range(m):
            if col in matched or detections[col].confidence >= .35:
                active[(frame_index, col)] = matched.get(col)
        prior_frame = frame_index
    return links


def stitch_trajectories(observations, anchors, *, member_count, camera_transforms=None):
    """Fill real detection nodes between agreeing trusted identity anchors.

    Input rows are (timestamp, detections, embeddings), with a matching mapping
    of member index to unexpanded detection box. Return box mappings and sets
    of inferred members, without changing anchors or any identity gallery.
    """
    if (isinstance(member_count, bool) or not isinstance(member_count, int)
            or not 1 <= member_count <= 20):
        raise ValueError('member_count must be between 1 and 20')
    if not observations or len(observations) != len(anchors):
        raise ValueError('observations and anchors must be nonempty and aligned')
    if camera_transforms is None:
        camera_transforms = (None,) * len(observations)
    if len(camera_transforms) != len(observations) or camera_transforms[0] is not None:
        raise ValueError('camera transforms must align and start with None')
    labels, anchored_nodes = {}, {}
    previous = -1.
    dimensions = set()
    for i, ((timestamp, detections, embeddings), frame_anchors) in enumerate(zip(observations, anchors)):
        if (isinstance(timestamp, bool) or not math.isfinite(timestamp)
                or timestamp < 0 or timestamp <= previous):
            raise ValueError('timestamps must be finite, nonnegative and increasing')
        previous = timestamp
        if len(detections) != len(embeddings):
            raise ValueError('detections and embeddings must align')
        dimensions.update(len(e.values) for e in embeddings if e is not None)
        for member, box in frame_anchors.items():
            if isinstance(member, bool) or not isinstance(member, int) or not 0 <= member < member_count:
                raise ValueError('anchor member is outside configured group')
            candidates = [j for j, d in enumerate(detections) if d.box == box]
            if len(candidates) != 1 or (i, candidates[0]) in labels:
                raise ValueError('each anchor must name one unique detection')
            node = (i, candidates[0])
            labels[node] = member
            anchored_nodes[i, member] = node
    if len(dimensions) > 1:
        raise ValueError('embedding dimensions must match')

    # ponytail: reciprocal local links leave ambiguous crossings split; a
    # multi-hypothesis path solver is warranted only by measured missed paths.
    links = (_directional_links(observations, camera_transforms)
             & _directional_links(observations, camera_transforms, reverse=True))
    original = frozenset(links)
    links = (_directional_links(observations, camera_transforms, reciprocal_history=original)
             & _directional_links(observations, camera_transforms, reverse=True,
                                  reciprocal_history=original))
    following = dict(links)
    preceded = {right for _, right in links}
    spans = []
    for start in sorted(following.keys() - preceded):
        path = [start]
        while path[-1] in following:
            path.append(following[path[-1]])
        known = [(p, labels[node]) for p, node in enumerate(path) if node in labels]
        for (left, member), (right, later_member) in zip(known, known[1:]):
            if member != later_member or right - left < 2:
                continue
            segment = path[left:right + 1]
            nodes = set(segment)
            if any((frame, member) in anchored_nodes and anchored_nodes[frame, member] not in nodes
                   for frame in range(segment[0][0], segment[-1][0] + 1)):
                continue
            spans.append((member, segment[1:-1]))
    # Enforce one member per frame across the entire timeline, not just each
    # local assignment. Reject both conflicting spans instead of choosing one.
    occupied, rejected = {}, set()
    for index, (member, nodes) in enumerate(spans):
        for node in nodes:
            key = (node[0], member)
            if key in occupied and occupied[key][1] != node:
                rejected.update((index, occupied[key][0]))
            else:
                occupied[key] = (index, node)
    result = [dict(a) for a in anchors]
    inferred = [set() for _ in observations]
    for index, (member, nodes) in enumerate(spans):
        if index in rejected:
            continue
        for frame, detection in nodes:
            result[frame][member] = observations[frame][1][detection].box
            inferred[frame].add(member)
    return tuple(result), tuple(frozenset(s) for s in inferred)


def visibility_states(observations, paths, inferred, *, member_index):
    """Classify framing evidence without promoting it to identity evidence."""
    states = []
    known = [i for i, path in enumerate(paths) if member_index in path]
    for i, ((timestamp, detections, _), path, inferred_members) in enumerate(
            zip(observations, paths, inferred)):
        box = path.get(member_index)
        if box is not None:
            detection = next((d for d in detections if d.box == box), None)
            states.append('partially_occluded' if member_index in inferred_members
                          or (detection is not None and detection.confidence < .35)
                          else 'visible')
            continue
        before = next((j for j in reversed(known) if j < i), None)
        after = next((j for j in known if j > i), None)
        nearest = paths[before][member_index] if before is not None else None
        at_edge = nearest is not None and (nearest.x <= .02 or nearest.y <= .02
            or nearest.x + nearest.width >= .98 or nearest.y + nearest.height >= .98)
        if at_edge and after is None:
            states.append('out_of_frame')
        elif (before is not None and after is not None and detections
              and observations[after][0] - observations[before][0] <= .5 + 1e-9):
            states.append('fully_occluded')
        else:
            states.append('unknown')
    return tuple(states)
