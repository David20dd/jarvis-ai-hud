from __future__ import annotations

from typing import Any, Dict, List

from .v101 import V101_STAGES


V102_VERSION = 102
V102_NAME = "Conversational Workspace"

V102_STAGES: List[Dict[str, Any]] = [
    *V101_STAGES,
    {
        "version": V102_VERSION,
        "name": V102_NAME,
        "capabilities": [
            "chat minimalista y adaptable",
            "herramientas unificadas",
            "proyectos con contexto",
            "canvas y artefactos persistentes",
            "memoria explicable",
            "investigación con fuentes",
            "misiones con aprobación humana",
            "voz, visión y documentos",
            "centro de calidad supervisado",
        ],
    },
]


V102_AREAS: Dict[str, Dict[str, Any]] = {
    "chat": {
        "label": "Chat",
        "description": "Conversación, razonamiento y respuesta multimodelo.",
        "route": "chat",
        "local_fallback": True,
    },
    "research": {
        "label": "Investigar",
        "description": "Búsqueda web, contraste, citas y biblioteca de fuentes.",
        "route": "research",
        "local_fallback": False,
    },
    "knowledge": {
        "label": "Conocimiento",
        "description": "Memoria, documentos y recuperación semántica.",
        "route": "knowledge",
        "local_fallback": True,
    },
    "canvas": {
        "label": "Canvas",
        "description": "Documentos, notas, código, tablas y artefactos.",
        "route": "workspace",
        "local_fallback": True,
    },
    "missions": {
        "label": "Misiones",
        "description": "Planes persistentes, checkpoints y aprobaciones.",
        "route": "missions",
        "local_fallback": True,
    },
    "voice": {
        "label": "Voz",
        "description": "Dictado, transcripción, lectura y Telegram multimedia.",
        "route": "voice",
        "local_fallback": True,
    },
    "quality": {
        "label": "Calidad",
        "description": "Diagnóstico, incidencias y mejora supervisada.",
        "route": "nexus",
        "local_fallback": True,
    },
}


def build_area_status(
    *,
    workspace_connected: bool,
    memory_connected: bool,
    generative_configured: bool,
    web_configured: bool,
    voice_input: bool,
    voice_output: bool,
    telegram_configured: bool,
    reliability_connected: bool,
) -> Dict[str, Dict[str, Any]]:
    """Return a stable UI-facing capability matrix without leaking secrets."""

    flags = {
        "chat": generative_configured,
        "research": generative_configured and web_configured,
        "knowledge": memory_connected,
        "canvas": workspace_connected,
        "missions": memory_connected,
        "voice": voice_input or voice_output,
        "quality": reliability_connected,
    }
    areas: Dict[str, Dict[str, Any]] = {}
    for key, definition in V102_AREAS.items():
        available = bool(flags.get(key))
        degraded = not available and bool(definition.get("local_fallback"))
        areas[key] = {
            **definition,
            "available": available,
            "degraded": degraded,
        }
    areas["voice"]["input"] = voice_input
    areas["voice"]["output"] = voice_output
    areas["voice"]["telegram"] = telegram_configured
    return areas


__all__ = [
    "V102_VERSION",
    "V102_NAME",
    "V102_STAGES",
    "V102_AREAS",
    "build_area_status",
]
