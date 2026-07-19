from __future__ import annotations

import copy
import json
import os
import shutil
import statistics
import threading
import time
from collections import OrderedDict, defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Callable, Deque, Dict, Iterable, List, Optional, Tuple, TypeVar

T = TypeVar("T")


def _json_clone(value: T) -> T:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))
    except Exception:
        try:
            return copy.deepcopy(value)
        except Exception:
            return value


class MemoryTTLCache:
    """Thread-safe L1 cache with bounded size and TTL eviction."""

    def __init__(self, max_items: int = 512) -> None:
        self.max_items = max(32, int(max_items))
        self._items: "OrderedDict[str, Tuple[float, Any]]" = OrderedDict()
        self._lock = threading.RLock()
        self.hits = 0
        self.misses = 0
        self.sets = 0
        self.evictions = 0

    def get(self, key: str) -> Optional[Any]:
        now = time.time()
        with self._lock:
            item = self._items.get(key)
            if item is None:
                self.misses += 1
                return None
            expires_at, value = item
            if expires_at <= now:
                self._items.pop(key, None)
                self.misses += 1
                self.evictions += 1
                return None
            self._items.move_to_end(key)
            self.hits += 1
            return _json_clone(value)

    def set(self, key: str, value: Any, ttl: int) -> None:
        expires_at = time.time() + max(1, int(ttl))
        with self._lock:
            self._items[key] = (expires_at, _json_clone(value))
            self._items.move_to_end(key)
            self.sets += 1
            while len(self._items) > self.max_items:
                self._items.popitem(last=False)
                self.evictions += 1

    def delete(self, key: str) -> None:
        with self._lock:
            self._items.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            total = self.hits + self.misses
            return {
                "items": len(self._items),
                "max_items": self.max_items,
                "hits": self.hits,
                "misses": self.misses,
                "sets": self.sets,
                "evictions": self.evictions,
                "hit_rate": round(self.hits / total, 4) if total else 0.0,
            }


class RedisLayer:
    """Optional Redis L2. It disables itself temporarily after failures."""

    def __init__(self, url: str, namespace: str = "jarvis:v23", failure_cooldown: int = 30) -> None:
        self.url = (url or "").strip()
        self.namespace = namespace
        self.failure_cooldown = max(5, int(failure_cooldown))
        self._client: Any = None
        self._lock = threading.RLock()
        self._disabled_until = 0.0
        self._last_error = ""
        self.hits = 0
        self.misses = 0
        self.sets = 0
        self.errors = 0

    @property
    def configured(self) -> bool:
        return bool(self.url)

    def _connect(self) -> Any:
        if not self.configured:
            return None
        if time.time() < self._disabled_until:
            return None
        with self._lock:
            if self._client is not None:
                return self._client
            try:
                import redis  # type: ignore

                self._client = redis.Redis.from_url(
                    self.url,
                    decode_responses=True,
                    socket_connect_timeout=2.0,
                    socket_timeout=2.5,
                    health_check_interval=30,
                    retry_on_timeout=True,
                )
                self._client.ping()
                self._last_error = ""
                return self._client
            except Exception as exc:
                self._client = None
                self.errors += 1
                self._last_error = str(exc)[:300]
                self._disabled_until = time.time() + self.failure_cooldown
                return None

    def _key(self, key: str) -> str:
        return f"{self.namespace}:{key}"

    def get_json(self, key: str) -> Optional[Any]:
        client = self._connect()
        if client is None:
            self.misses += 1
            return None
        try:
            raw = client.get(self._key(key))
            if not raw:
                self.misses += 1
                return None
            self.hits += 1
            return json.loads(raw)
        except Exception as exc:
            self.errors += 1
            self._last_error = str(exc)[:300]
            self._disabled_until = time.time() + self.failure_cooldown
            self._client = None
            self.misses += 1
            return None

    def set_json(self, key: str, value: Any, ttl: int) -> bool:
        client = self._connect()
        if client is None:
            return False
        try:
            client.setex(self._key(key), max(1, int(ttl)), json.dumps(value, ensure_ascii=False, default=str))
            self.sets += 1
            return True
        except Exception as exc:
            self.errors += 1
            self._last_error = str(exc)[:300]
            self._disabled_until = time.time() + self.failure_cooldown
            self._client = None
            return False

    def delete(self, key: str) -> None:
        client = self._connect()
        if client is None:
            return
        try:
            client.delete(self._key(key))
        except Exception:
            self.errors += 1

    def ping(self) -> Dict[str, Any]:
        started = time.perf_counter()
        client = self._connect()
        if client is None:
            return {
                "configured": self.configured,
                "ok": False,
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                "detail": self._last_error or ("no configurado" if not self.configured else "temporalmente deshabilitado"),
            }
        try:
            ok = bool(client.ping())
            return {"configured": True, "ok": ok, "latency_ms": round((time.perf_counter() - started) * 1000, 2)}
        except Exception as exc:
            return {"configured": True, "ok": False, "detail": str(exc)[:300], "latency_ms": round((time.perf_counter() - started) * 1000, 2)}

    def stats(self) -> Dict[str, Any]:
        total = self.hits + self.misses
        return {
            "configured": self.configured,
            "connected": self._client is not None and time.time() >= self._disabled_until,
            "hits": self.hits,
            "misses": self.misses,
            "sets": self.sets,
            "errors": self.errors,
            "hit_rate": round(self.hits / total, 4) if total else 0.0,
            "disabled_for_seconds": max(0, round(self._disabled_until - time.time(), 1)),
            "last_error": self._last_error,
        }


@dataclass
class CircuitState:
    state: str = "closed"
    failures: int = 0
    successes: int = 0
    opened_at: float = 0.0
    last_failure_at: float = 0.0
    last_success_at: float = 0.0
    last_error: str = ""
    probe_in_progress: bool = False


class CircuitRegistry:
    def __init__(self, failure_threshold: int = 3, recovery_seconds: int = 45) -> None:
        self.failure_threshold = max(1, int(failure_threshold))
        self.recovery_seconds = max(5, int(recovery_seconds))
        self._states: Dict[str, CircuitState] = defaultdict(CircuitState)
        self._lock = threading.RLock()

    def allow(self, name: str) -> bool:
        now = time.time()
        with self._lock:
            state = self._states[name]
            if state.state == "closed":
                return True
            if state.state == "open":
                if now - state.opened_at < self.recovery_seconds:
                    return False
                if state.probe_in_progress:
                    return False
                state.state = "half_open"
                state.probe_in_progress = True
                return True
            if state.state == "half_open":
                if state.probe_in_progress:
                    return False
                state.probe_in_progress = True
                return True
            return True

    def success(self, name: str) -> None:
        with self._lock:
            state = self._states[name]
            state.successes += 1
            state.failures = 0
            state.state = "closed"
            state.last_success_at = time.time()
            state.probe_in_progress = False
            state.last_error = ""

    def failure(self, name: str, error: Any = "") -> None:
        with self._lock:
            state = self._states[name]
            state.failures += 1
            state.last_failure_at = time.time()
            state.last_error = str(error)[:300]
            state.probe_in_progress = False
            if state.state == "half_open" or state.failures >= self.failure_threshold:
                state.state = "open"
                state.opened_at = time.time()

    def snapshot(self) -> Dict[str, Any]:
        now = time.time()
        with self._lock:
            return {
                name: {
                    "state": state.state,
                    "failures": state.failures,
                    "successes": state.successes,
                    "last_error": state.last_error,
                    "retry_in_seconds": max(0, round(self.recovery_seconds - (now - state.opened_at), 1)) if state.state == "open" else 0,
                    "last_failure_at": state.last_failure_at,
                    "last_success_at": state.last_success_at,
                }
                for name, state in self._states.items()
            }


class MetricsRegistry:
    def __init__(self, max_samples: int = 500) -> None:
        self.max_samples = max(50, int(max_samples))
        self.started_at = time.time()
        self._durations: Dict[str, Deque[float]] = defaultdict(lambda: deque(maxlen=self.max_samples))
        self._status: Dict[str, Dict[str, int]] = defaultdict(lambda: {"success": 0, "error": 0, "timeout": 0, "cancelled": 0})
        self._lock = threading.RLock()

    def record(self, operation: str, duration_ms: float, status: str = "success") -> None:
        status = status if status in {"success", "error", "timeout", "cancelled"} else "error"
        with self._lock:
            self._durations[operation].append(max(0.0, float(duration_ms)))
            self._status[operation][status] += 1

    @staticmethod
    def _percentile(values: List[float], percent: float) -> float:
        if not values:
            return 0.0
        ordered = sorted(values)
        index = (len(ordered) - 1) * percent
        lower = int(index)
        upper = min(lower + 1, len(ordered) - 1)
        fraction = index - lower
        return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            operations: Dict[str, Any] = {}
            for name, samples in self._durations.items():
                values = list(samples)
                counts = dict(self._status[name])
                total = sum(counts.values())
                operations[name] = {
                    "samples": len(values),
                    "requests": total,
                    "success_rate": round(counts.get("success", 0) / total, 4) if total else 0.0,
                    "errors": counts.get("error", 0),
                    "timeouts": counts.get("timeout", 0),
                    "cancelled": counts.get("cancelled", 0),
                    "avg_ms": round(statistics.fmean(values), 2) if values else 0.0,
                    "p50_ms": round(self._percentile(values, 0.50), 2),
                    "p95_ms": round(self._percentile(values, 0.95), 2),
                    "max_ms": round(max(values), 2) if values else 0.0,
                }
            return {
                "uptime_seconds": round(time.time() - self.started_at, 1),
                "operations": operations,
            }


@dataclass
class _Flight:
    event: threading.Event = field(default_factory=threading.Event)
    result: Any = None
    error: Optional[BaseException] = None
    followers: int = 0


class SingleFlight:
    """Collapses identical concurrent work into a single execution."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._flights: Dict[str, _Flight] = {}
        self.collapsed = 0

    def run(self, key: str, function: Callable[[], T], wait_timeout: float = 120.0) -> T:
        leader = False
        with self._lock:
            flight = self._flights.get(key)
            if flight is None:
                flight = _Flight()
                self._flights[key] = flight
                leader = True
            else:
                flight.followers += 1
                self.collapsed += 1

        if leader:
            try:
                flight.result = function()
            except BaseException as exc:
                flight.error = exc
            finally:
                flight.event.set()
                with self._lock:
                    self._flights.pop(key, None)
        else:
            if not flight.event.wait(timeout=max(1.0, float(wait_timeout))):
                raise TimeoutError("La operación compartida superó el tiempo máximo de espera")

        if flight.error is not None:
            raise flight.error
        return _json_clone(flight.result)

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {"active": len(self._flights), "collapsed_requests": self.collapsed}


class RuntimeSupport:
    def __init__(
        self,
        *,
        redis_url: str = "",
        l1_items: int = 512,
        circuit_failures: int = 3,
        circuit_recovery_seconds: int = 45,
        metrics_samples: int = 500,
    ) -> None:
        self.cache = MemoryTTLCache(l1_items)
        self.redis = RedisLayer(redis_url)
        self.circuits = CircuitRegistry(circuit_failures, circuit_recovery_seconds)
        self.metrics = MetricsRegistry(metrics_samples)
        self.singleflight = SingleFlight()

    def cache_get(self, key: str) -> Tuple[Optional[Any], str]:
        value = self.cache.get(key)
        if value is not None:
            return value, "memory"
        value = self.redis.get_json(key)
        if value is not None:
            self.cache.set(key, value, 60)
            return value, "redis"
        return None, "miss"

    def cache_set(self, key: str, value: Any, ttl: int) -> None:
        self.cache.set(key, value, ttl)
        self.redis.set_json(key, value, ttl)

    def snapshot(self) -> Dict[str, Any]:
        return {
            "cache": {"memory": self.cache.stats(), "redis": self.redis.stats()},
            "circuits": self.circuits.snapshot(),
            "metrics": self.metrics.summary(),
            "singleflight": self.singleflight.stats(),
            "disk": disk_status(os.getcwd()),
        }


def compact_messages(messages: Iterable[Dict[str, Any]], max_chars: int, max_messages: int) -> List[Dict[str, Any]]:
    items = [dict(item) for item in messages]
    if not items:
        return []
    max_chars = max(4000, int(max_chars))
    max_messages = max(4, int(max_messages))

    system = [item for item in items if item.get("role") == "system"][:1]
    non_system = [item for item in items if item.get("role") != "system"][-max_messages:]
    selected = system + non_system

    total = 0
    result_reversed: List[Dict[str, Any]] = []
    for item in reversed(selected):
        content = item.get("content", "")
        if not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False, default=str)
        remaining = max_chars - total
        if remaining <= 0:
            break
        if len(content) > remaining:
            if item.get("role") == "system":
                content = content[:remaining]
            else:
                content = "…[contexto compactado]…\n" + content[-max(0, remaining - 26):]
        new_item = dict(item)
        new_item["content"] = content
        result_reversed.append(new_item)
        total += len(content)
    return list(reversed(result_reversed))


def disk_status(path: str) -> Dict[str, Any]:
    try:
        usage = shutil.disk_usage(path)
        return {
            "ok": usage.free > 50 * 1024 * 1024,
            "total_mb": round(usage.total / 1024 / 1024, 1),
            "used_mb": round(usage.used / 1024 / 1024, 1),
            "free_mb": round(usage.free / 1024 / 1024, 1),
            "used_percent": round(usage.used / usage.total * 100, 2) if usage.total else 0.0,
        }
    except Exception as exc:
        return {"ok": False, "detail": str(exc)[:300]}
