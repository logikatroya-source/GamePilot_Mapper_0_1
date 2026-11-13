import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from profile_utils import normalize_profile


class ProfileNormalizationTests(unittest.TestCase):
    def test_legacy_single_point_profile_migrates(self):
        result = normalize_profile({"point": [120, 240], "clicks": 2, "gather_wait": 7, "repeats": 4})
        self.assertEqual(len(result["steps"]), 1)
        self.assertEqual(result["steps"][0]["x"], 120)
        self.assertEqual(result["steps"][0]["wait"], 7.0)
        self.assertEqual(result["repeats"], 4)

    def test_multiple_steps_are_preserved_and_clamped(self):
        result = normalize_profile({"steps": [
            {"name": "Bush", "x": 20, "y": 30, "clicks": 99, "wait": 0},
            {"name": "Ore", "x": 40, "y": 50, "clicks": 2, "wait": 8}
        ]})
        self.assertEqual(len(result["steps"]), 2)
        self.assertEqual(result["steps"][0]["clicks"], 5)
        self.assertEqual(result["steps"][0]["wait"], 0.1)
        self.assertEqual(result["steps"][1]["name"], "Ore")

    def test_negative_coordinates_are_rejected(self):
        with self.assertRaises(ValueError):
            normalize_profile({"steps": [{"x": -1, "y": 3}]})


if __name__ == "__main__":
    unittest.main()
