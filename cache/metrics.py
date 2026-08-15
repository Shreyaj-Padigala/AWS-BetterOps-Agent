"""Cache counters.

Hit rate is one of the metrics the Phase 15 evaluation platform reports, so it is
recorded from the start rather than bolted on later. These are per-process, in-memory
counters: cheap, lock-protected, and reset when the process restarts. Aggregating them
across ECS tasks is CloudWatch's job, not this module's.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass


@dataclass(frozen=True)
class CacheStats:
    hits: int
    misses: int
    errors: int
    invalidations: int

    @property
    def lookups(self) -> int:
        return self.hits + self.misses

    @property
    def hit_rate(self) -> float:
        return round(self.hits / self.lookups, 4) if self.lookups else 0.0

    def to_dict(self) -> dict[str, float | int]:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "errors": self.errors,
            "invalidations": self.invalidations,
            "lookups": self.lookups,
            "hit_rate": self.hit_rate,
        }


class _Counters:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0
        self.errors = 0
        self.invalidations = 0

    def record_hit(self) -> None:
        with self._lock:
            self.hits += 1

    def record_miss(self) -> None:
        with self._lock:
            self.misses += 1

    def record_error(self) -> None:
        with self._lock:
            self.errors += 1

    def record_invalidation(self, count: int = 1) -> None:
        with self._lock:
            self.invalidations += count

    def snapshot(self) -> CacheStats:
        with self._lock:
            return CacheStats(self.hits, self.misses, self.errors, self.invalidations)

    def reset(self) -> None:
        with self._lock:
            self.hits = self.misses = self.errors = self.invalidations = 0


_counters = _Counters()

record_hit = _counters.record_hit
record_miss = _counters.record_miss
record_error = _counters.record_error
record_invalidation = _counters.record_invalidation
snapshot = _counters.snapshot
reset = _counters.reset
