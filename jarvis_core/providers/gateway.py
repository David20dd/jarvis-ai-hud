from __future__ import annotations

import time
from dataclasses import asdict
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .base import BaseProvider, ProviderError, ProviderModel, ProviderRequest, ProviderResult


INTENT_PROVIDER_PREFERENCES: Dict[str, List[str]] = {
    "research": ["gemini", "openai", "groq", "compatible", "ollama"],
    "documents": ["gemini", "openai", "groq", "compatible", "ollama"],
    "coding": ["openai", "groq", "gemini", "compatible", "ollama"],
    "code": ["openai", "groq", "gemini", "compatible", "ollama"],
    "math": ["groq", "openai", "gemini", "compatible", "ollama"],
    "writing": ["openai", "gemini", "groq", "compatible", "ollama"],
    "planning": ["openai", "gemini", "groq", "compatible", "ollama"],
    "general": ["groq", "openai", "gemini", "compatible", "ollama"],
}

MODE_PROVIDER_PREFERENCES: Dict[str, List[str]] = {
    "fast": ["groq", "gemini", "openai", "compatible", "ollama"],
    "research": ["gemini", "openai", "groq", "compatible", "ollama"],
    "writing": ["openai", "gemini", "groq", "compatible", "ollama"],
    "math": ["groq", "openai", "gemini", "compatible", "ollama"],
    "private": ["ollama", "groq", "openai", "gemini", "compatible"],
}


class MultiProviderGateway:
    def __init__(self, providers: Sequence[BaseProvider], *, order: Optional[Sequence[str]] = None) -> None:
        self.providers: Dict[str, BaseProvider] = {provider.name: provider for provider in providers}
        self.order = [item for item in (order or []) if item in self.providers]
        for name in self.providers:
            if name not in self.order:
                self.order.append(name)
        self.last_routes: List[Dict[str, Any]] = []

    def close(self) -> None:
        for provider in self.providers.values():
            provider.close()

    def configured_names(self) -> List[str]:
        return [name for name in self.order if self.providers[name].configured]

    def _preference(self, request: ProviderRequest) -> List[str]:
        if request.preferred_provider and request.preferred_provider in self.providers:
            preferred = [request.preferred_provider]
        else:
            preferred = []
        mode_order = MODE_PROVIDER_PREFERENCES.get(request.mode, [])
        intent_order = INTENT_PROVIDER_PREFERENCES.get(request.intent, INTENT_PROVIDER_PREFERENCES["general"])
        configured_order = self.order
        merged: List[str] = []
        for name in [*preferred, *mode_order, *intent_order, *configured_order]:
            if name in self.providers and name not in merged:
                merged.append(name)
        return merged

    @staticmethod
    def _model_score(model: ProviderModel, request: ProviderRequest, provider_name: str, rank: int) -> float:
        score = 1.0 - min(rank, 10) * 0.055
        score += model.quality * 0.32
        score += model.speed * (0.32 if request.mode == "fast" else 0.14)
        score -= model.cost * 0.08
        if request.intent == "research" and "research" in model.capabilities:
            score += 0.22
        if request.intent in {"coding", "code"} and "coding" in model.capabilities:
            score += 0.22
        if request.mode == "private" and provider_name == "ollama":
            score += 0.7
        return score

    def route_preview(self, request: ProviderRequest) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for rank, name in enumerate(self._preference(request)):
            provider = self.providers[name]
            if not provider.configured:
                rows.append({"provider": name, "configured": False, "score": -1, "models": []})
                continue
            models = []
            provider_stats = provider.stats.snapshot()
            observed = int(provider_stats.get("requests", 0) or 0)
            success_rate = float(provider_stats.get("success_rate", 0.0) or 0.0)
            average_latency = float(provider_stats.get("average_latency_ms", 0.0) or 0.0)
            reliability_adjustment = ((success_rate - 0.5) * 0.24) if observed else 0.0
            latency_adjustment = -min(0.18, average_latency / 60000.0) if observed else 0.0
            circuits = provider.runtime.circuits.snapshot()
            for model in provider.model_candidates(request):
                circuit = circuits.get(provider.circuit_name(model.id), {})
                circuit_state = str(circuit.get("state", "closed"))
                circuit_adjustment = -3.0 if circuit_state == "open" else (-0.15 if circuit_state == "half_open" else 0.0)
                score = self._model_score(model, request, name, rank) + reliability_adjustment + latency_adjustment + circuit_adjustment
                models.append({
                    "model": model.id,
                    "score": round(score, 4),
                    "capabilities": sorted(model.capabilities),
                    "circuit": circuit_state,
                    "observed_success_rate": success_rate if observed else None,
                    "observed_latency_ms": average_latency if observed else None,
                })
            rows.append({
                "provider": name,
                "configured": True,
                "score": max([m["score"] for m in models], default=-1),
                "models": models,
                "stats": provider_stats,
            })
        return sorted(rows, key=lambda item: item.get("score", -1), reverse=True)

    def candidates(self, request: ProviderRequest) -> Iterable[Tuple[BaseProvider, ProviderModel, float]]:
        preview = self.route_preview(request)
        for provider_row in preview:
            provider = self.providers[provider_row["provider"]]
            if not provider.configured:
                continue
            model_by_id = {model.id: model for model in provider.model_candidates(request)}
            for model_row in sorted(provider_row.get("models", []), key=lambda item: item["score"], reverse=True):
                model = model_by_id.get(model_row["model"])
                if model:
                    yield provider, model, float(model_row["score"])

    def generate(self, request: ProviderRequest, *, max_attempts: int = 8) -> Tuple[ProviderResult, List[Dict[str, Any]]]:
        attempts: List[Dict[str, Any]] = []
        started = time.perf_counter()
        for index, (provider, model, score) in enumerate(self.candidates(request), start=1):
            if index > max(1, int(max_attempts)):
                break
            attempt_started = time.perf_counter()
            try:
                result = provider.generate(request, model)
                attempts.append({
                    "provider": provider.name,
                    "model": model.id,
                    "status": "completed",
                    "latency_ms": round(result.latency_ms, 2),
                    "score": round(score, 4),
                })
                self.last_routes = attempts[-30:]
                result.metadata["gateway_latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
                result.metadata["attempt_count"] = len(attempts)
                return result, attempts
            except ProviderError as exc:
                attempts.append({
                    "provider": provider.name,
                    "model": model.id,
                    "status": "failed",
                    "category": exc.category,
                    "retry_after_seconds": exc.retry_after_seconds,
                    "detail": str(exc)[:300],
                    "latency_ms": round((time.perf_counter() - attempt_started) * 1000, 2),
                    "score": round(score, 4),
                })
            except Exception as exc:
                attempts.append({
                    "provider": provider.name,
                    "model": model.id,
                    "status": "failed",
                    "category": "unknown",
                    "detail": str(exc)[:300],
                    "latency_ms": round((time.perf_counter() - attempt_started) * 1000, 2),
                    "score": round(score, 4),
                })
        self.last_routes = attempts[-30:]
        retry_after = min(
            [int(item.get("retry_after_seconds", 30)) for item in attempts if item.get("retry_after_seconds")],
            default=30,
        )
        raise ProviderError(
            "Ningún proveedor generativo configurado pudo completar la solicitud.",
            provider="gateway",
            category="all_failed",
            retry_after_seconds=retry_after,
        )

    def snapshot(self) -> Dict[str, Any]:
        return {
            "configured": self.configured_names(),
            "order": self.order,
            "providers": {
                name: {
                    **provider.health(deep=False),
                    "models_detail": [asdict(model) | {"capabilities": sorted(model.capabilities)} for model in provider.models],
                }
                for name, provider in self.providers.items()
            },
            "last_routes": self.last_routes,
        }
