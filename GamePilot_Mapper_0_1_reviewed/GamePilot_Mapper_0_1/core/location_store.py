import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path


_WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def safe_profile_name(name):
    value = re.sub(r"[^\w -]", "", str(name), flags=re.UNICODE).strip()
    value = re.sub(r"[ .-]+", "_", value).strip("_")
    if not value:
        value = "Location"
    if value.upper() in _WINDOWS_RESERVED:
        value = f"_{value}"
    return value[:64]


class LocationStore:
    """JSON-backed local profiles with atomic writes and safe profile names."""
    def __init__(self, root=None):
        self.root = Path(root or (Path.home() / "GamePilotMapper" / "Locations"))
        self.root.mkdir(parents=True, exist_ok=True)
        self.name = None
        self.data = None

    @property
    def path(self):
        if not self.name:
            return None
        return self.root / self.name / "map.json"

    def list_profiles(self):
        return sorted(p.name for p in self.root.iterdir() if p.is_dir() and (p / "map.json").is_file())

    def create(self, name, overwrite=False):
        safe = safe_profile_name(name)
        target = self.root / safe / "map.json"
        if target.exists() and not overwrite:
            raise FileExistsError(f"Профиль «{safe}» уже существует")
        self.name = safe
        self.data = {
            "schema_version": 1,
            "name": safe,
            "created": datetime.now(timezone.utc).isoformat(),
            "updated": datetime.now(timezone.utc).isoformat(),
            "base_set": False,
            "observations": [],
            "resources": [],
            "landmarks": [],
            "odometry": {"dx": 0.0, "dy": 0.0},
            "note": "Experimental local map; coordinates are not calibrated.",
        }
        self.save()
        return self.data

    def load(self, name):
        safe = safe_profile_name(name)
        path = self.root / safe / "map.json"
        if not path.is_file():
            raise FileNotFoundError(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Некорректный формат профиля")
        data.setdefault("schema_version", 1)
        for key in ("observations", "resources", "landmarks"):
            if not isinstance(data.get(key), list):
                data[key] = []
        self.name, self.data = safe, data
        return data

    def save(self):
        if self.data is None or self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data["updated"] = datetime.now(timezone.utc).isoformat()
        fd, temp_name = tempfile.mkstemp(prefix="map_", suffix=".tmp", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(self.data, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_name, self.path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def add_observation(self, observation, limit=500):
        if self.data is None:
            return
        self.data["observations"].append(observation)
        del self.data["observations"][:-limit]
        self.save()

    def add_resource(self, resource, limit=2000):
        if self.data is None:
            return
        self.data["resources"].append(resource)
        del self.data["resources"][:-limit]
        self.save()

    def set_base(self):
        if self.data is not None:
            self.data["base_set"] = True
            self.data["base_time"] = datetime.now(timezone.utc).isoformat()
            self.save()
