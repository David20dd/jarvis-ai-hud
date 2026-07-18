from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence

import httpx


class ProviderError(RuntimeError):
    """Normalized provider failure used by the multi-provider gateway."""

    def __init__(
        self,
        message: str,
        *,
        provider: str,
        model: str = "",
        category: str = "unknown",
        retry_after_seconds: int = 30,
        status_code: Optional[int] = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.model = model
        self.category = category
        self.retry_after_seconds = max(1, int(retry_after_seconds))
        self.status_code = status_code


@dataclass(slots=True)
class ProviderRequest:
    messages: List[Dict[str, str]]
    intent: str = "general"
    mode: str = "auto"
    temperature: float = 0.25
    max_tokens: int = 1200
    preferred_provider: str = ""
    required_capabilities: set[str] = field(default_factory=set)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ProviderResult:
    provider: str
    model: str
    text: str
    usage: Dict[str, int] = field(default_factory=dict)
    latency_ms: float = 0.0
    finish_reason: str = "stop"
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def route_model(self) -> str:
        return f"{self.provider}:{self.model}" if self.model else self.provider


@dataclass(slots=True)
class ProviderModel:
    id: str
    capabilities: set[str] = field(default_factory=lambda: {"text"})
    quality: float = 0.7
    speed: float = 0.7
    cost: float = 0.5
    context: int = 0


class ProviderStats:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.requests = 0
        self.successes = 0
        self.failures = 0
        self.total_latency_ms = 0.0
        self.last_latency_ms = 0.0
        self.last_error = ""
        self.last_model = ""
        self.last_success_at = 0.0
        self.last_failure_at = 0.0
        self.prompt_tokens = 0
        self.completion_tokens = 0

    def success(self, result: ProviderResult) -> None:
        with self._lock:
            self.requests += 1
            self.successes += 1
            self.total_latency_ms += result.latency_ms
            self.last_latency_ms = result.latency_ms
            self.last_error = ""
            self.last_model = result.model
            self.last_success_at = time.time()
            self.prompt_tokens += int(result.usage.get("prompt_tokens", 0) or 0)
            self.completion_tokens += int(result.usage.get("completion_tokens", 0) or 0)

    def failure(self, error: Exception, latency_ms: float, model: str = "") -> None:
        with self._lock:
            self.requests += 1
            self.failures += 1
            self.total_latency_ms += max(0.0, latency_ms)
            self.last_latency_ms = max(0.0, latency_ms)
            self.last_error = str(error)[:300]
            self.last_model = model
            self.last_failure_at = time.time()

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "requests": self.requests,
                "successes": self.successes,
                "failures": self.failures,
                "success_rate": round(self.successes / self.requests, 4) if self.requests else 0.0,
                "average_latency_ms": round(self.total_latency_ms / self.requests, 2) if self.requests else 0.0,
                "last_latency_ms": round(self.last_latency_ms, 2),
                "last_error": self.last_error,
                "last_model": self.last_model,
                "last_success_at": self.last_success_at,
                "last_failure_at": self.last_failure_at,
                "prompt_tokens": self.prompt_tokens,
                "completion_tokens": self.completion_tokens,
            }


class BaseProvider:
    name = "base"
    label = "Base"
    capabilities: set[str] = {"text"}

    def __init__(
        self,
        *,
        models: Sequence[ProviderModel],
        runtime: Any,
        timeout_seconds: int = 45,
        base_url: str = "",
        api_key: str = "",
    ) -> None:
        self.models = list(models)
        self.runtime = runtime
        self.timeout_seconds = max(5, int(timeout_seconds))
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key.strip()
        self.stats = ProviderStats()
        limits = httpx.Limits(max_keepalive_connections=10, max_connections=20, keepalive_expiry=30.0)
        self.http = httpx.Client(
            timeout=httpx.Timeout(self.timeout_seconds, connect=min(8.0, float(self.timeout_seconds))),
            follow_redirects=True,
            limits=limits,
            headers={"User-Agent": "JARVIS-MultiProvider/19.0"},
        )

    @property
    def configured(self) -> bool:
        return bool(self.models)

    def close(self) -> None:
        try:
            self.http.close()
        except Exception:
            pass

    def circuit_name(self, model: str) -> str:
        return f"provider:{self.name}:{model}"

    def model_candidates(self, request: ProviderRequest) -> Iterable[ProviderModel]:
        required = request.required_capabilities or {"text"}
        for model in self.models:
            if required.issubset(model.capabilities | self.capabilities):
                yield model

    def generate(self, request: ProviderRequest, model: ProviderModel) -> ProviderResult:
        raise NotImplementedError

    def health(self, deep: bool = False) -> Dict[str, Any]:
        return {
            "provider": self.name,
            "label": self.label,
            "configured": self.configured,
            "models": [m.id for m in self.models],
            "capabilities": sorted(self.capabilities),
            "stats": self.stats.snapshot(),
            "deep_checked": bool(deep),
        }

    @staticmethod
    def normalize_messages(messages: Sequence[Dict[str, Any]], max_chars: int = 60000) -> List[Dict[str, str]]:
        output: List[Dict[str, str]] = []
        used = 0
        for item in messages:
            role = str(item.get("role", "user"))
            if role not in {"system", "user", "assistant"}:
                continue
            content = item.get("content", "")
            if isinstance(content, list):
                content = "\n".join(str(part) for part in content)
            text = str(content or "").strip()
            if not text:
                continue
            remaining = max_chars - used
            if remaining <= 0:
                break
            text = text[:remaining]
            output.append({"role": role, "content": text})
            used += len(text)
        return output

    @staticmethod
    def classify_http_error(response: httpx.Response, provider: str, model: str) -> ProviderError:
        status = response.status_code
        try:
            payload = response.json()
            detail = payload.get("error", payload)
            if isinstance(detail, dict):
                message = str(detail.get("message") or detail.get("status") or detail)
            else:
                message = str(detail)
        except Exception:
            message = response.text[:500] or f"HTTP {status}"
        retry_after = 30
        raw_retry = response.headers.get("retry-after", "").strip()
        if raw_retry.isdigit():
            retry_after = max(1, int(raw_retry))
        if status == 429:
            category = "rate_limit"
        elif status in {401, 403}:
            category = "authentication"
            retry_after = 300
        elif status in {408, 409, 425, 500, 502, 503, 504}:
            category = "temporary"
        elif status == 400:
            category = "bad_request"
        else:
            category = "http_error"
        return ProviderError(
            message[:600],
            provider=provider,
            model=model,
            category=category,
            retry_after_seconds=retry_after,
            status_code=status,
        )
