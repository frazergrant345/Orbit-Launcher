"""Persistent usage-frequency tracking, used to rank frequently launched
results higher over time (apps, settings panels, etc.)."""
import json
import math

from .config import CONFIG_DIR, USAGE_FILE

# Points added to a result's score per previous launch, tapering off via log
# so one huge outlier doesn't permanently dominate the list.
_BOOST_PER_USE = 8.0
_MAX_BOOST = 60.0


class UsageStore:
    def __init__(self):
        self._counts = self._load()

    def _load(self) -> dict:
        try:
            return json.loads(USAGE_FILE.read_text())
        except (OSError, json.JSONDecodeError):
            return {}

    def _save(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        try:
            USAGE_FILE.write_text(json.dumps(self._counts, indent=2) + "\n")
        except OSError:
            pass

    def record(self, result_id: str):
        if not result_id:
            return
        self._counts[result_id] = self._counts.get(result_id, 0) + 1
        self._save()

    def boost(self, result_id: str) -> float:
        if not result_id:
            return 0.0
        count = self._counts.get(result_id, 0)
        if count <= 0:
            return 0.0
        return min(_MAX_BOOST, math.log1p(count) * _BOOST_PER_USE)
