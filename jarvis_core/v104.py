from __future__ import annotations

import re
import time
from typing import Any, Dict, Iterable, List

from .v102 import V102_STAGES


V104_VERSION = 104
V104_NAME = "Adaptive Intelligence Workspace"

V104_STAGES: List[Dict[str, Any]] = [
    *V102_STAGES,
    {
        "version": V104_VERSION,
        "name": V104_NAME,
        "capabilities": [
            "búsqueda global segura",
            "sidebar adaptable",
            "Canvas dividido",
            "memoria explicable",
            "progreso de razonamiento visible",
            "densidad y tipografía configurables",
            "recuperación de conversaciones",
            "espacio de trabajo por proyecto",
        ],
    },
]


def search_tokens(value: str) -> List[str]:
    return [token for token in re.findall(r"[a-záéíóúñ0-9]{2,}", str(value or "").lower())]


def lexical_score(query: str, *values: str) -> float:
    wanted = set(search_tokens(query))
    if not wanted:
        return 0.0
    present = set(search_tokens(" ".join(str(value or "") for value in values)))
    return round(len(wanted & present) / max(1, len(wanted)), 5)


def compact_snippet(value: str, query: str = "", limit: int = 220) -> str:
    clean = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(clean) <= limit:
        return clean
    terms = search_tokens(query)
    lowered = clean.lower()
    offsets = [lowered.find(term) for term in terms if lowered.find(term) >= 0]
    start = max(0, (min(offsets) if offsets else 0) - limit // 4)
    end = min(len(clean), start + limit)
    prefix = "…" if start else ""
    suffix = "…" if end < len(clean) else ""
    return f"{prefix}{clean[start:end].strip()}{suffix}"


def explain_memory(memory: Dict[str, Any], *, query: str = "") -> Dict[str, Any]:
    updated = float(memory.get("updated_at") or memory.get("created_at") or 0)
    age_days = max(0, int((time.time() - updated) / 86400)) if updated else None
    score = float(memory.get("score") or 0)
    lexical = float(memory.get("lexical_score") or 0)
    semantic = float(memory.get("semantic_score") or 0)
    reasons: List[str] = []
    if query and lexical > 0:
        reasons.append("coincide con palabras importantes de la consulta")
    if query and semantic > 0.25:
        reasons.append("su significado es cercano a la consulta")
    if int(memory.get("importance") or 0) >= 4:
        reasons.append("fue marcado como importante")
    if memory.get("project_name"):
        reasons.append(f"pertenece al proyecto {memory.get('project_name')}")
    if not reasons:
        reasons.append("forma parte de la memoria autorizada de esta sesión")
    return {
        "id": memory.get("id"),
        "content": memory.get("content", ""),
        "project_name": memory.get("project_name", "") or "General",
        "memory_type": memory.get("memory_type") or memory.get("category") or "contexto",
        "source": memory.get("source") or "usuario",
        "importance": int(memory.get("importance") or 3),
        "confidence": round(float(memory.get("confidence") or 1.0), 3),
        "match": {"score": score, "lexical": lexical, "semantic": semantic},
        "age_days": age_days,
        "reasons": reasons,
        "controls": {"editable": False, "deletable": True, "session_isolated": True},
    }


def rank_results(results: Iterable[Dict[str, Any]], limit: int = 30) -> List[Dict[str, Any]]:
    clean = [dict(item) for item in results if item.get("title") or item.get("snippet")]
    clean.sort(key=lambda item: (float(item.get("score") or 0), float(item.get("updated_at") or 0)), reverse=True)
    return clean[: max(1, min(int(limit), 50))]


__all__ = [
    "V104_VERSION",
    "V104_NAME",
    "V104_STAGES",
    "search_tokens",
    "lexical_score",
    "compact_snippet",
    "explain_memory",
    "rank_results",
]
