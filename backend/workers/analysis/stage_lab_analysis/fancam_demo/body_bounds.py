"""Conservative visible pose extent; missing points do not prove completeness."""
from ..detection import NormalizedBox


def visible_body_box(box, keypoints):
    points = [p for p in keypoints if p.confidence >= .5
              and box.x-.25*box.width <= p.x <= box.x+1.25*box.width
              and box.y-.15*box.height <= p.y <= box.y+1.15*box.height]
    if not points:
        return box
    left = min(box.x, *(p.x for p in points))
    top = min(box.y, *(p.y for p in points))
    right = max(box.x+box.width, *(p.x for p in points))
    bottom = max(box.y+box.height, *(p.y for p in points))
    return NormalizedBox(left, top, right-left, bottom-top)
