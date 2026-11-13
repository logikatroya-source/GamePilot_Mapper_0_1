import json
import tempfile
import unittest
from core.location_store import LocationStore, safe_profile_name


class StoreTests(unittest.TestCase):
    def test_create_set_base_and_reload(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LocationStore(directory)
            store.create("Test Location")
            self.assertFalse(store.data["base_set"])
            store.set_base()
            self.assertTrue(store.data["base_set"])
            self.assertTrue(store.path.exists())
            other = LocationStore(directory)
            other.load("Test Location")
            self.assertTrue(other.data["base_set"])

    def test_duplicate_profile_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LocationStore(directory)
            store.create("alpha")
            store.data["note"] = "keep me"
            store.save()
            with self.assertRaises(FileExistsError):
                store.create("alpha")
            store.load("alpha")
            self.assertEqual(store.data["note"], "keep me")

    def test_safe_names(self):
        self.assertEqual(safe_profile_name("../../CON"), "_CON")
        self.assertTrue(len(safe_profile_name("x" * 100)) <= 64)

    def test_observation_history_is_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LocationStore(directory)
            store.create("bounded")
            for i in range(8):
                store.add_observation({"n": i}, limit=5)
            self.assertEqual([x["n"] for x in store.data["observations"]], [3, 4, 5, 6, 7])


if __name__ == "__main__":
    unittest.main()
