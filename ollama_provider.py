from __future__ import annotations

import time
from typing import Any, Dict

from .base import BaseProvider, ProviderError, ProviderModel, ProviderRequest, ProviderResult


class OpenAICompatibleProvider(BaseProvider):
    name = "compatible"
    label = "Proveedor compatible"
    capabilities = {"text", "coding", "reasoning"}

    def __init__(self, *, base_url: str, api_key: str, models: list[ProviderModel], runtime: Any, timeout_seconds: int = 45) -> None:
        super().__init__(
            models=models if base_url else [],
            runtime=runtime,
            timeout_seconds=timeout_seconds,
            base_url=base_url,
            api_key=api_key,
        )

    def generate(self, request: ProviderRequest, model: ProviderModel) -> ProviderResult:
        started = time.perf_counter()
        circuit = self.circuit_name(model.id)
        if not self.runtime.circuits.allow(circuit):
            raise ProviderError("Circuito temporalmente abierto", provider=self.name, model=model.id, category="circuit_open")
        try:
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            response = self.http.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json={
                    "model": model.id,
                    "messages": self.normalize_messages(request.messages),
                    "temperature": request.temperature,
                    "max_tokens": request.max_tokens,
                    "stream": False,
                },
            )
            if response.is_error:
                raise self.classify_http_error(response, self.name, model.id)
            payload: Dict[str, Any] = response.json()
            text = str(payload.get("choices", [{}])[0].get("message", {}).get("content", "")).strip()
            if not text:
                raise ProviderError("Respuesta vacía", provider=self.name, model=model.id, category="empty")
            raw_usage = payload.get("usage", {}) or {}
            result = ProviderResult(
                provider=self.name,
                model=model.id,
                text=text,
                usage={
                    "prompt_tokens": int(raw_usage.get("prompt_tokens", 0) or 0),
                    "completion_tokens": int(raw_usage.get("completion_tokens", 0) or 0),
                    "total_tokens": int(raw_usage.get("total_tokens", 0) or 0),
                },
                latency_ms=(time.perf_counter() - started) * 1000,
                finish_reason=str(payload.get("choices", [{}])[0].get("finish_reason", "stop") or "stop"),
            )
            self.runtime.circuits.success(circuit)
            self.runtime.metrics.record(circuit, result.latency_ms, "success")
            self.stats.success(result)
            return result
        except Exception as exc:
            elapsed = (time.perf_counter() - started) * 1000
            error = exc if isinstance(exc, ProviderError) else ProviderError(str(exc), provider=self.name, model=model.id)
            self.runtime.circuits.failure(circuit, error)
            self.runtime.metrics.record(circuit, elapsed, "timeout" if "timeout" in str(error).lower() else "error")
            self.stats.failure(error, elapsed, model.id)
            raise error
