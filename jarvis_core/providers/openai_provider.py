from __future__ import annotations

import time
from typing import Any, Dict, List

from .base import BaseProvider, ProviderError, ProviderModel, ProviderRequest, ProviderResult


class OpenAIProvider(BaseProvider):
    name = "openai"
    label = "OpenAI"
    capabilities = {"text", "reasoning", "coding", "research"}

    def __init__(self, *, api_key: str, models: list[ProviderModel], runtime: Any, timeout_seconds: int = 45, base_url: str = "https://api.openai.com/v1") -> None:
        super().__init__(
            models=models if api_key else [],
            runtime=runtime,
            timeout_seconds=timeout_seconds,
            base_url=base_url,
            api_key=api_key,
        )

    @staticmethod
    def _input(messages: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for message in messages:
            role = message["role"]
            if role == "system":
                role = "developer"
            items.append({
                "role": role,
                "content": [{"type": "input_text", "text": message["content"]}],
            })
        return items

    @staticmethod
    def _extract_text(payload: Dict[str, Any]) -> str:
        direct = payload.get("output_text")
        if direct:
            return str(direct).strip()
        chunks: List[str] = []
        for item in payload.get("output", []) or []:
            for content in item.get("content", []) or []:
                if content.get("type") in {"output_text", "text"} and content.get("text"):
                    chunks.append(str(content["text"]))
        return "\n".join(chunks).strip()

    def generate(self, request: ProviderRequest, model: ProviderModel) -> ProviderResult:
        started = time.perf_counter()
        circuit = self.circuit_name(model.id)
        if not self.runtime.circuits.allow(circuit):
            raise ProviderError("Circuito temporalmente abierto", provider=self.name, model=model.id, category="circuit_open")
        try:
            messages = self.normalize_messages(request.messages)
            body: Dict[str, Any] = {
                "model": model.id,
                "input": self._input(messages),
                "max_output_tokens": request.max_tokens,
            }
            response = self.http.post(
                f"{self.base_url}/responses",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json=body,
            )
            if response.is_error:
                raise self.classify_http_error(response, self.name, model.id)
            payload = response.json()
            text = self._extract_text(payload)
            if not text:
                raise ProviderError("Respuesta vacía", provider=self.name, model=model.id, category="empty")
            raw_usage = payload.get("usage", {}) or {}
            usage = {
                "prompt_tokens": int(raw_usage.get("input_tokens", raw_usage.get("prompt_tokens", 0)) or 0),
                "completion_tokens": int(raw_usage.get("output_tokens", raw_usage.get("completion_tokens", 0)) or 0),
                "total_tokens": int(raw_usage.get("total_tokens", 0) or 0),
            }
            if usage["total_tokens"] <= 0:
                usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]
            result = ProviderResult(
                provider=self.name,
                model=model.id,
                text=text,
                usage=usage,
                latency_ms=(time.perf_counter() - started) * 1000,
                finish_reason=str(payload.get("status", "completed") or "completed"),
                metadata={"response_id": str(payload.get("id", ""))},
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
