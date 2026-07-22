from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List
from urllib.parse import urlsplit, urlunsplit


OFFICIAL_HINTS = (
    ".gov", ".gob", ".edu", ".int", "who.int", "worldbank.org",
    "imf.org", "un.org", "oecd.org", "europa.eu", "docs.",
)


def _clean_url(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    try:
        parsed = urlsplit(value)
        return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/"), parsed.query, ""))
    except Exception:
        return value.split("#", 1)[0].rstrip("/")


def _quality(item: Dict[str, Any]) -> float:
    url = str(item.get("url", "")).lower()
    title = str(item.get("title", "")).strip()
    snippet = str(item.get("snippet", item.get("body", ""))).strip()
    score = 0.35
    if any(hint in url for hint in OFFICIAL_HINTS):
        score += 0.3
    if title:
        score += 0.12
    if len(snippet) >= 120:
        score += 0.13
    if url.startswith("https://"):
        score += 0.06
    return round(min(1.0, score), 3)


def build_query_variants(query: str, limit: int = 4) -> List[str]:
    query = re.sub(r"\s+", " ", query or "").strip()
    if not query:
        return []
    variants = [query]
    lowered = query.lower()
    if not any(term in lowered for term in ("fuente", "oficial", "datos", "informe")):
        variants.append(f"{query} fuentes oficiales datos")
    if not any(term in lowered for term in ("actual", "reciente", "2026")):
        variants.append(f"{query} información reciente")
    variants.append(f"{query} análisis evidencia")
    seen = set()
    result = []
    for value in variants:
        key = value.casefold()
        if key not in seen:
            seen.add(key)
            result.append(value)
        if len(result) >= max(1, min(limit, 6)):
            break
    return result


@dataclass(slots=True)
class Evidence:
    id: str
    title: str
    url: str
    snippet: str
    query: str
    provider: str
    quality: float
    retrieved_at: float

    def as_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "query": self.query,
            "provider": self.provider,
            "quality": self.quality,
            "retrieved_at": self.retrieved_at,
        }


class ResearchCollector:
    """Builds a traceable evidence pack from an existing search adapter."""

    def collect(
        self,
        query: str,
        search: Callable[[str, int], Dict[str, Any]],
        *,
        max_sources: int = 12,
        queries: int = 4,
    ) -> Dict[str, Any]:
        max_sources = max(2, min(int(max_sources), 30))
        variants = build_query_variants(query, queries)
        evidence: List[Evidence] = []
        attempts: List[Dict[str, Any]] = []
        seen = set()
        started = time.perf_counter()
        for variant in variants:
            try:
                payload = search(variant, max(4, min(8, max_sources))) or {}
                rows: Iterable[Dict[str, Any]] = payload.get("results", [])
                count = 0
                for item in rows:
                    url = _clean_url(str(item.get("url", item.get("href", ""))))
                    title = str(item.get("title", "")).strip()
                    snippet = str(item.get("snippet", item.get("body", ""))).strip()
                    identity = url or hashlib.sha256(f"{title}|{snippet[:240]}".encode("utf-8")).hexdigest()
                    if not identity or identity in seen:
                        continue
                    seen.add(identity)
                    count += 1
                    evidence.append(
                        Evidence(
                            id=hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16],
                            title=title or "Fuente sin título",
                            url=url,
                            snippet=snippet[:2400],
                            query=variant,
                            provider=str(item.get("provider") or payload.get("provider") or "web")[:80],
                            quality=_quality({"url": url, "title": title, "snippet": snippet}),
                            retrieved_at=time.time(),
                        )
                    )
                    if len(evidence) >= max_sources:
                        break
                attempts.append({"query": variant, "status": "completed", "results": count})
            except Exception as exc:
                attempts.append({"query": variant, "status": "failed", "detail": f"{type(exc).__name__}: {exc}"[:300]})
            if len(evidence) >= max_sources:
                break
        evidence.sort(key=lambda item: (item.quality, len(item.snippet)), reverse=True)
        return {
            "query": query,
            "queries": variants,
            "evidence": [item.as_dict() for item in evidence[:max_sources]],
            "attempts": attempts,
            "source_count": min(len(evidence), max_sources),
            "official_or_primary_count": sum(1 for item in evidence[:max_sources] if item.quality >= 0.75),
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "limitations": [] if evidence else ["No fue posible recuperar fuentes verificables en este intento."],
        }

    @staticmethod
    def as_context(pack: Dict[str, Any], max_chars: int = 24000) -> str:
        lines = [f"Consulta: {pack.get('query', '')}", "Evidencia recuperada:"]
        for index, item in enumerate(pack.get("evidence", []), 1):
            lines.append(f"[{index}] {item.get('title', 'Fuente')} — calidad {item.get('quality', 0)}")
            if item.get("url"):
                lines.append(str(item["url"]))
            lines.append(str(item.get("snippet", "")))
        return "\n".join(lines)[:max_chars]
