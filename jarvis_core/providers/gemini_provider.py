from __future__ import annotations

import time
from typing import Any, Dict, List
from urllib.parse import quote

from .base import BaseProvider, ProviderError, ProviderModel, ProviderRequest, ProviderResult


class GeminiProvider(BaseProvider):
    name = "gemini"
    label = "Google Gemini"
    capabilities = {"text", "research", "reasoning", "coding", "long_context"}

    def __init__(self, *, api_key: str, models: list[ProviderModel], runtime: Any, timeout_seconds: int = 45, api_version: str = "v1beta") -> None:
        super().__init__(
            models=models if api_key else [],
            runtime=runtime,
            timeout_seconds=timeout_seconds,
            base_url=f"https://generativelanguage.googleapis.com/{api_version}",
            api_key=api_key,
        )

    @staticmethod
    def _payload(messages: List[Dict[str, str]], request: ProviderRequest) -> Dict[str, Any]:
        system_parts: List[str] = []
        contents: List[Dict[str, Any]] = []
        for message in messages:
            role = message["role"]
            if role == "system":
                system_parts.append(message["content"])
                continue
            gemini_role = "model" if role == "assistant" else "user"
            contents.append({"role": gemini_role, "parts": [{"text": message["content"]}]})
        body: Dict[str, Any] = {
            "contents": contents or [{"role": "user", "parts": [{"text": "Responde en español."}]}],
            "generationConfig": {
                "temperature": request.temperature,
                "maxOutputTokens": request.max_tokens,
            },
        }
        if system_parts:
            body["systemInstruction"] = {"parts": [{"text": "\n\n".join(system_parts)}]}
        return body

    @staticmethod
    def _extract_text(payload: Dict[str, Any]) -> str:
        chunks: List[str] = []
        for candidate in payload.get("candidates", []) or []:
            content = candidate.get("content", {}) or {}
            for part in content.get("parts", []) or []:
                if part.get("text"):
                    chunks.append(str(part["text"]))
            if chunks:
                break
        return "\n".join(chunks).strip()

    def generate(self, request: ProviderRequest, model: ProviderModel) -> ProviderResult:
        started = time.perf_counter()
        circuit = self.circuit_name(model.id)
        if not self.runtime.circuits.allow(circuit):
            raise ProviderError("Circuito temporalmente abierto", provider=self.name, model=model.id, category="circuit_open")
        try:
            encoded_model = quote(model.id, safe="-._/")
            response = self.http.post(
                f"{self.base_url}/models/{encoded_model}:generateContent",
                headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"},
                json=self._payload(self.normalize_messages(request.messages), request),
            )
            if response.is_error:
                raise self.classify_http_error(response, self.name, model.id)
            payload = response.json()
            text = self._extract_text(payload)
            if not text:
                feedback = payload.get("promptFeedback", {}) or {}
                raise ProviderError(f"Respuesta vacía: {feedback}", provider=self.name, model=model.id, category="empty")
            raw_usage = payload.get("usageMetadata", {}) or {}
            usage = {
                "prompt_tokens": int(raw_usage.get("promptTokenCount", 0) or 0),
                "completion_tokens": int(raw_usage.get("candidatesTokenCount", 0) or 0),
                "total_tokens": int(raw_usage.get("totalTokenCount", 0) or 0),
            }
            candidate = (payload.get("candidates") or [{}])[0]
            result = ProviderResult(
                provider=self.name,
                model=model.id,
                text=text,
                usage=usage,
                latency_ms=(time.perf_counter() - started) * 1000,
                finish_reason=str(candidate.get("finishReason", "STOP") or "STOP"),
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
