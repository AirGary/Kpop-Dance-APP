"""Conservative geometry fusion; caller owns identity validation.

Mask overlap is not identity evidence. A mask may only enlarge a currently
accepted detection, never shrink it or independently recover an identity.
"""
from ..detection import NormalizedBox
import math


class MaskContinuity:
    """Bounded camera inference, never an identity or gallery update.

    A failed link disarms propagation until identity and mask agree again.
    One second is an experimental limit, measured from identity, not masks.
    """

    def __init__(self):
        self.mask = self.body = None
        self.identity_time = self.timestamp = -1.

    @staticmethod
    def _compatible(a, b):
        return (a is not None and b is not None and a.iou(b) >= .5
                and 2/3 <= a.width/b.width <= 1.5
                and 2/3 <= a.height/b.height <= 1.5)

    def update(self, timestamp, mask, identity_box):
        if not math.isfinite(timestamp) or timestamp < 0 or timestamp <= self.timestamp:
            raise ValueError('timestamps must be finite, nonnegative and increasing')
        step = timestamp-self.timestamp
        self.timestamp = timestamp
        if identity_box is not None:
            body = validated_body_box(mask, identity_box)
            self.identity_time = timestamp
            self.mask = mask if self._compatible(mask, identity_box) else None
            self.body = body if self.mask is not None else None
            return body, False
        if (timestamp-self.identity_time <= 1. and step <= .2+1e-9
                and self.body is not None and self._compatible(mask, self.mask)):
            # Translate the last body extent without zooming into a partial mask.
            dx = mask.x+mask.width/2-self.mask.x-self.mask.width/2
            dy = mask.y+mask.height/2-self.mask.y-self.mask.height/2
            body = self.body
            x, y = body.x+dx, body.y+dy
            if 0 <= x <= 1-body.width and 0 <= y <= 1-body.height:
                self.body = NormalizedBox(x, y, body.width, body.height)
                self.mask = mask
                return self.body, True
        self.mask = self.body = None
        return None, False


def validated_body_box(mask, identity_box):
    if identity_box is None or mask is None:
        return identity_box
    # Reject disconnected/merged-person geometry. These are experimental
    # geometry limits, not calibrated confidence or identity thresholds.
    if (mask.iou(identity_box) < .3
            or mask.width > identity_box.width * 1.5
            or mask.height > identity_box.height * 1.5):
        return identity_box
    left = min(mask.x, identity_box.x)
    top = min(mask.y, identity_box.y)
    right = max(mask.x + mask.width, identity_box.x + identity_box.width)
    bottom = max(mask.y + mask.height, identity_box.y + identity_box.height)
    if (left == identity_box.x and top == identity_box.y
            and right == identity_box.x + identity_box.width
            and bottom == identity_box.y + identity_box.height):
        return identity_box
    return NormalizedBox(left, top, min(1-left, right-left),
                         min(1-top, bottom-top))
