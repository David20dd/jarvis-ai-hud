from __future__ import annotations

import time
from typing import Any, Dict

from .base import BaseProvider, ProviderError, ProviderModel, ProviderRequest, ProviderResult


class OllamaProvider(BaseProvider):
    name = "ollama"
    label = "Ollama"
    capabilities = {"text", "local", "privacy", "coding"}

    def __init__(self, *, base_url: str, models: list[ProviderModel], runtime: Any, timeout_seconds: int = 90, api_key: str = "") -> None:
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
                f"{self.base_url}/api/chat",
                headers=headers,
                json={
                    "model": model.id,
                    "messages": self.normalize_messages(request.messages),
                    "stream": False,
                    "options": {"temperature": request.temperature, "num_predict": request.max_tokens},
                },
            )
            if response.is_error:
                raise self.classify_http_error(response, self.name, model.id)
            payload: Dict[str, Any] = response.json()
            text = str(payload.get("message", {}).get("content", "")).strip()
            if not text:
                raise ProviderError("Respuesta vacía", provider=self.name, model=model.id, category="empty")
            prompt_tokens = int(payload.get("prompt_eval_count", 0) or 0)
            completion_tokens = int(payload.get("eval_count", 0) or 0)
            result = ProviderResult(
                provider=self.name,
                model=model.id,
                text=text,
                usage={
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                },
                latency_ms=(time.perf_counter() - started) * 1000,
                finish_reason="stop" if payload.get("done") else "unknown",
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
