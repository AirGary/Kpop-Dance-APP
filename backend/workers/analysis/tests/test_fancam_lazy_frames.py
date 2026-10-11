import cv2
import numpy as np
import pytest

from stage_lab_analysis.fancam_demo.lazy_frames import LazyFrames


def test_cache_is_bounded_and_revisit_decodes_same_frame(tmp_path):
    path = tmp_path / "source.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10, (32,32))
    for i in range(20):
        writer.write(np.full((32,32,3), i*10, np.uint8))
    writer.release()
    frames = LazyFrames(path, 2, 5, image_size=32)
    try:
        first = frames[0].clone()
        assert len(frames) == 10
        for i in range(10):
            assert frames[i].shape == (3,32,32)
            assert len(frames.cache) <= 2
        assert np.allclose(first.numpy(), frames[0].numpy())
        with pytest.raises(IndexError):
            frames[10]
    finally:
        frames.close()
