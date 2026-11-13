import unittest
import cv2
import numpy as np
from mapping.landmark_tracker import LandmarkTracker


class TrackerTests(unittest.TestCase):
    def test_first_frame_initializes_without_claiming_tracking(self):
        tracker = LandmarkTracker()
        frame = np.zeros((160, 200, 3), dtype=np.uint8)
        result = tracker.update(frame)
        self.assertFalse(result["tracked"])
        self.assertEqual(result["total_dx"], 0.0)

    def test_translation_is_tracked_on_textured_scene(self):
        rng = np.random.default_rng(7)
        gray = rng.integers(0, 255, (240, 320), dtype=np.uint8)
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        first = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        matrix = np.float32([[1, 0, 5], [0, 1, 3]])
        shifted_gray = cv2.warpAffine(gray, matrix, (320, 240))
        second = cv2.cvtColor(shifted_gray, cv2.COLOR_GRAY2BGR)
        tracker = LandmarkTracker()
        tracker.update(first)
        result = tracker.update(second)
        self.assertTrue(result["tracked"])
        self.assertAlmostEqual(result["dx"], 5, delta=1.5)
        self.assertAlmostEqual(result["dy"], 3, delta=1.5)


if __name__ == "__main__":
    unittest.main()
