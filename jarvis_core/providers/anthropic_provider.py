from __future__ import annotations

import time
from typing import Any, Dict, List, Tuple

from .base import BaseProvider, ProviderModel, ProviderRequest, ProviderResult


class AnthropicProvider(BaseProvider):
    """Native Anthropic Claude Messages API adapter.

    The implementation deliberately uses plain HTTP through the shared httpx
    client, so JARVIS does not require an additional SDK and can keep a single
    dependency surface for all providers.
    """

    name = "anthropic"
    label = "Anthropic Claude"
    capabilities = {"text", "reasoning", "coding", "research", "writing", "long_context"}

    def __init__(
        self,
        *,
        api_key: str,
        models: list[ProviderModel],
        runtime: Any,
        timeout_seconds: int = 45,
        base_url: str = "https://api.anthropic.com",
        api_version: str = "2023-06-01",
        prompt_cache: bool = True,
        cache_ttl: str = "5m",
    ) -> None:
        super().__init__(
            models=models if api_key else [],
            runtime=runtime,
            timeout_seconds=timeout_seconds,
            base_url=base_url,
            api_key=api_key,
        )
        self.api_version = api_version.strip() or "2023-06-01"
        self.prompt_cache = bool(prompt_cache)
        self.cache_ttl = "1h" if str(cache_ttl).strip().lower() == "1h" else "5m"

    @staticmethod
    def _split_messages(messages: List[Dict[str, str]]) -> Tuple[str, List[Dict[str, str]]]:
        system_parts: List[str] = []
        conversation: List[Dict[str, str]] = []

        for item in messages:
            role = item.get("role", "user")
            text = str(item.get("content", "") or "").strip()
            if not text:
                continue
            if role == "system":
                system_parts.append(text)
                continue
            normalized_role = "assistant" if role == "assistant" else "user"
            if conversation and conversation[-1]["role"] == normalized_role:
                conversation[-1]["content"] += "\n\n" + text
            else:
                conversation.append({"role": normalized_role, "content": text})

        if not conversation:
            conversation = [{"role": "user", "content": "Continúa con la tarea indicada."}]
        elif conversation[0]["role"] == "assistant":
            conversation.insert(0, {"role": "user", "content": "Usa el contexto disponible y responde a la solicitud."})

        return "\n\n".join(system_parts).strip(), conversation

    def generate(self, request: ProviderRequest, model: ProviderModel) -> ProviderResult:
        started = time.perf_counter()
        circuit = self.circuit_name(model.id)
        if not self.runtime.circuits.allow(circuit):
            raise RuntimeError(f"Circuito temporalmente abierto para {self.name}:{model.id}")

        messages = self.normalize_messages(request.messages)
        system_text, conversation = self._split_messages(messages)
        payload: Dict[str, Any] = {
            "model": model.id,
            "max_tokens": max(64, int(request.max_tokens)),
            "messages": conversation,
        }

        # Claude's Messages API supports reusable prompt prefixes. We cache the
        # stable system block, while dynamic user/tool output stays uncached.
        if system_text:
            if self.prompt_cache:
                payload["system"] = [
                    {
                        "type": "text",
                        "text": system_text,
                        "cache_control": {"type": "ephemeral", "ttl": self.cache_ttl},
                    }
                ]
            else:
                payload["system"] = system_text

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": self.api_version,
            "content-type": "application/json",
        }

        try:
            response = self.http.post(f"{self.base_url}/v1/messages", headers=headers, json=payload)
            if response.status_code >= 400:
                raise self.classify_http_error(response, self.name, model.id)
            data = response.json()
            text = "\n".join(
                str(block.get("text", ""))
                for block in data.get("content", [])
                if isinstance(block, dict) and block.get("type") == "text" and block.get("text")
            ).strip()
            if not text:
                raise RuntimeError("Claude respondió sin bloques de texto utilizables.")

            usage_raw = data.get("usage") or {}
            input_tokens = int(usage_raw.get("input_tokens", 0) or 0)
            output_tokens = int(usage_raw.get("output_tokens", 0) or 0)
            cache_creation = int(usage_raw.get("cache_creation_input_tokens", 0) or 0)
            cache_read = int(usage_raw.get("cache_read_input_tokens", 0) or 0)
            usage = {
                "prompt_tokens": input_tokens,
                "completion_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
                "cache_creation_input_tokens": cache_creation,
                "cache_read_input_tokens": cache_read,
            }
            result = ProviderResult(
                provider=self.name,
                model=model.id,
                text=text,
                usage=usage,
                latency_ms=(time.perf_counter() - started) * 1000,
                finish_reason=str(data.get("stop_reason") or "stop"),
                metadata={
                    "message_id": data.get("id", ""),
                    "prompt_cache_enabled": self.prompt_cache,
                    "cache_ttl": self.cache_ttl if self.prompt_cache else "off",
                },
            )
            self.runtime.circuits.success(circuit)
            self.stats.success(result)
            self.runtime.metrics.record(circuit, result.latency_ms, "success")
            return result
        except Exception as exc:
            latency = (time.perf_counter() - started) * 1000
            self.runtime.circuits.failure(circuit, str(exc)[:300])
            self.stats.failure(exc, latency, model.id)
            self.runtime.metrics.record(circuit, latency, "error")
            raise

    def health(self, deep: bool = False) -> Dict[str, Any]:
        base = super().health(deep=deep)
        base.update(
            {
                "api_version": self.api_version,
                "prompt_cache": self.prompt_cache,
                "cache_ttl": self.cache_ttl if self.prompt_cache else "off",
            }
        )
        if deep and self.configured:
            headers = {"x-api-key": self.api_key, "anthropic-version": self.api_version}
            started = time.perf_counter()
            try:
                response = self.http.get(f"{self.base_url}/v1/models", headers=headers, params={"limit": 5})
                base["deep_ok"] = response.status_code < 400
                base["deep_status_code"] = response.status_code
                base["deep_latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
            except Exception as exc:
                base["deep_ok"] = False
                base["deep_error"] = str(exc)[:220]
        return base
