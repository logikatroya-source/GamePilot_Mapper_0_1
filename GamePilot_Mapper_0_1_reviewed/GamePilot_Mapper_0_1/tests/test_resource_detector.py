import tempfile
import unittest
from pathlib import Path
import cv2
import numpy as np
from vision.resource_detector import ResourceDetector


class DetectorTests(unittest.TestCase):
    def test_finds_embedded_template(self):
        rng = np.random.default_rng(42)
        template = rng.integers(0, 255, (32, 36, 3), dtype=np.uint8)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "template.png"
            self.assertTrue(cv2.imwrite(str(path), template))
            detector = ResourceDetector(path)
            frame = np.zeros((150, 180, 3), dtype=np.uint8)
            frame[51:83, 72:108] = template
            hits = detector.detect(frame, threshold=0.95, scales=[1.0])
            self.assertTrue(hits)
            self.assertEqual(hits[0][1:], (72, 51, 36, 32))

    def test_empty_frame_returns_no_hits(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "template.png"
            cv2.imwrite(str(path), np.ones((20, 20, 3), dtype=np.uint8))
            detector = ResourceDetector(path)
            self.assertEqual(detector.detect(None), [])


if __name__ == "__main__":
    unittest.main()
