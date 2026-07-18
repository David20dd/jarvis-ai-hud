from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable, Dict, Iterable, Optional


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    label: str
    category: str
    description: str
    risk: str = "low"
    requires_approval: bool = False
    local: bool = True
    timeout_seconds: int = 15


DEFAULT_TOOL_DEFINITIONS: Dict[str, ToolDefinition] = {
    "web_search": ToolDefinition("web_search", "Búsqueda web", "research", "Busca información pública y reúne fuentes.", local=False, timeout_seconds=25),
    "calculator": ToolDefinition("calculator", "Calculadora", "math", "Realiza cálculos deterministas sin consumir tokens."),
    "sympy_solve": ToolDefinition("sympy_solve", "Motor simbólico", "math", "Resuelve ecuaciones y expresiones algebraicas con SymPy."),
    "memory_save": ToolDefinition("memory_save", "Guardar memoria", "memory", "Conserva una preferencia o dato útil para el proyecto.", risk="medium", requires_approval=True),
    "memory_search": ToolDefinition("memory_search", "Buscar memoria", "memory", "Recupera recuerdos relacionados con la solicitud."),
    "memory_delete": ToolDefinition("memory_delete", "Eliminar memoria", "memory", "Elimina un recuerdo guardado.", risk="high", requires_approval=True),
    "reminder_create": ToolDefinition("reminder_create", "Crear recordatorio", "automation", "Programa un recordatorio sencillo.", risk="medium", requires_approval=True),
    "reminder_list": ToolDefinition("reminder_list", "Listar recordatorios", "automation", "Consulta recordatorios activos."),
    "reminder_cancel": ToolDefinition("reminder_cancel", "Cancelar recordatorio", "automation", "Cancela un recordatorio existente.", risk="medium", requires_approval=True),
    "current_datetime": ToolDefinition("current_datetime", "Fecha y hora", "utility", "Obtiene fecha y hora local del servidor."),
    "document_search": ToolDefinition("document_search", "Buscar documentos", "documents", "Recupera contenido de documentos indexados."),
}


class ToolRegistry:
    def __init__(self, functions: Optional[Dict[str, Callable[..., Any]]] = None) -> None:
        self.functions: Dict[str, Callable[..., Any]] = dict(functions or {})
        self.definitions: Dict[str, ToolDefinition] = dict(DEFAULT_TOOL_DEFINITIONS)

    def bind(self, functions: Dict[str, Callable[..., Any]]) -> None:
        self.functions = dict(functions)

    def available(self) -> Iterable[str]:
        return self.functions.keys()

    def snapshot(self) -> Dict[str, Any]:
        tools = []
        for name in sorted(set(self.definitions) | set(self.functions)):
            definition = self.definitions.get(name) or ToolDefinition(
                name=name,
                label=name.replace("_", " ").title(),
                category="general",
                description="Herramienta registrada en JARVIS.",
            )
            row = asdict(definition)
            row["available"] = name in self.functions
            tools.append(row)
        categories: Dict[str, int] = {}
        for item in tools:
            if item["available"]:
                categories[item["category"]] = categories.get(item["category"], 0) + 1
        return {"tools": tools, "categories": categories, "available_count": sum(1 for item in tools if item["available"])}
