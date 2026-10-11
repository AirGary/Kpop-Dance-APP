"""Bounded, timestamp-preserving frame access for offline model experiments."""
from collections import OrderedDict
import math

import cv2
import numpy as np
from PIL import Image


class LazyFrames:
    def __init__(self, source, duration, sample_fps, image_size=1024):
        if not (math.isfinite(duration) and duration > 0 and
                math.isfinite(sample_fps) and 0 < sample_fps <= 30):
            raise ValueError("invalid sampling configuration")
        self.capture = cv2.VideoCapture(str(source))
        self.fps = self.capture.get(cv2.CAP_PROP_FPS)
        self.width = int(self.capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self.capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        count = self.capture.get(cv2.CAP_PROP_FRAME_COUNT)
        if not self.capture.isOpened() or self.fps <= 0 or count <= 0:
            self.close()
            raise ValueError("unreadable video")
        self.count = math.ceil(min(duration, count/self.fps)*sample_fps)
        self.sample_fps = sample_fps
        self.image_size = image_size
        self.cache = OrderedDict()
        self.position = -1

    def __len__(self):
        return self.count

    def __getitem__(self, index):
        import torch
        if not 0 <= index < self.count:
            raise IndexError(index)
        if index in self.cache:
            return self.cache[index]
        target = round(index*self.fps/self.sample_fps)
        if target <= self.position:
            self.capture.set(cv2.CAP_PROP_POS_FRAMES, target)
            self.position = target-1
        while self.position < target:
            if not self.capture.grab():
                raise ValueError("video ended during sampling")
            self.position += 1
        ok, frame = self.capture.retrieve()
        if not ok:
            raise ValueError("frame decoding failed")
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        # Match upstream JPEG loader's PIL resizing (bicubic), including
        # antialiasing when small distant people are downsampled.
        rgb = np.asarray(Image.fromarray(rgb).resize((self.image_size, self.image_size)))
        array = rgb.astype(np.float32)/255
        array = (array-np.array([.485,.456,.406], dtype=np.float32))/np.array([.229,.224,.225], dtype=np.float32)
        tensor = torch.from_numpy(array).permute(2,0,1).contiguous()
        self.cache[index] = tensor
        while len(self.cache) > 2:
            self.cache.popitem(last=False)
        return tensor

    def close(self):
        self.capture.release()
