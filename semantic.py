from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Any, Dict, Iterable, List, Sequence


@dataclass(frozen=True)
class ProfessionalRole:
    id: str
    name: str
    mission: str
    capabilities: tuple[str, ...]
    preferred_providers: tuple[str, ...]
    icon: str

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["capabilities"] = list(self.capabilities)
        data["preferred_providers"] = list(self.preferred_providers)
        return data


ROLE_CATALOG: Dict[str, ProfessionalRole] = {
    "director": ProfessionalRole(
        id="director",
        name="Director de misión",
        mission="Define alcance, prioridades, entregables y criterios de éxito.",
        capabilities=("planning", "coordination", "risk", "quality"),
        preferred_providers=("anthropic", "openai", "gemini", "groq"),
        icon="◇",
    ),
    "researcher": ProfessionalRole(
        id="researcher",
        name="Investigador",
        mission="Localiza, contrasta y organiza evidencia relevante.",
        capabilities=("research", "web", "sources", "synthesis"),
        preferred_providers=("gemini", "openai", "anthropic", "groq"),
        icon="⌕",
    ),
    "analyst": ProfessionalRole(
        id="analyst",
        name="Analista",
        mission="Convierte datos y documentos en hallazgos, riesgos y decisiones.",
        capabilities=("documents", "data", "reasoning", "math"),
        preferred_providers=("anthropic", "openai", "gemini", "groq"),
        icon="▦",
    ),
    "engineer": ProfessionalRole(
        id="engineer",
        name="Ingeniero de soluciones",
        mission="Diseña, implementa y comprueba soluciones técnicas.",
        capabilities=("coding", "debugging", "architecture", "testing"),
        preferred_providers=("openai", "anthropic", "groq", "gemini"),
        icon="⌘",
    ),
    "economist": ProfessionalRole(
        id="economist",
        name="Economista",
        mission="Interpreta indicadores, causalidad, escenarios y efectos económicos.",
        capabilities=("economics", "statistics", "forecasting", "policy"),
        preferred_providers=("anthropic", "openai", "gemini", "groq"),
        icon="◫",
    ),
    "writer": ProfessionalRole(
        id="writer",
        name="Redactor ejecutivo",
        mission="Transforma el trabajo técnico en entregables claros y profesionales.",
        capabilities=("writing", "editing", "reports", "presentation"),
        preferred_providers=("anthropic", "openai", "gemini", "groq"),
        icon="✎",
    ),
    "auditor": ProfessionalRole(
        id="auditor",
        name="Auditor de calidad",
        mission="Comprueba cobertura, coherencia, riesgos, cifras y formato final.",
        capabilities=("verification", "quality", "compliance", "consistency"),
        preferred_providers=("anthropic", "openai", "gemini", "groq"),
        icon="✓",
    ),
    "project_manager": ProfessionalRole(
        id="project_manager",
        name="Gestor de proyecto",
        mission="Organiza dependencias, responsables, hitos y seguimiento.",
        capabilities=("planning", "tasks", "dependencies", "tracking"),
        preferred_providers=("anthropic", "openai", "gemini", "groq"),
        icon="◆",
    ),
}


INTENT_ROLE_MAP: Dict[str, tuple[str, ...]] = {
    "research": ("director", "researcher", "analyst", "writer", "auditor"),
    "documents": ("director", "analyst", "writer", "auditor"),
    "math": ("director", "analyst", "auditor"),
    "code": ("director", "engineer", "auditor", "writer"),
    "planning": ("director", "project_manager", "analyst", "auditor"),
    "writing": ("director", "writer", "auditor"),
    "memory": ("director", "analyst", "auditor"),
    "reminders": ("director", "project_manager", "auditor"),
    "general": ("director", "analyst", "writer", "auditor"),
}


KEYWORD_ROLES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("inflación", "pib", "economía", "finanzas", "desempleo", "monetaria", "mercado"), "economist"),
    (("código", "python", "javascript", "api", "error", "css", "html", "backend", "frontend"), "engineer"),
    (("informe", "documento", "presentación", "redacta", "escribe", "resumen ejecutivo"), "writer"),
    (("cronograma", "responsables", "hitos", "proyecto", "plan de trabajo"), "project_manager"),
    (("fuentes", "investiga", "actual", "reciente", "comparar evidencia"), "researcher"),
)


def _unique(values: Iterable[str]) -> List[str]:
    seen: set[str] = set()
    result: List[str] = []
    for value in values:
        if value and value not in seen:
            result.append(value)
            seen.add(value)
    return result


def infer_complexity(objective: str, intent: str = "general") -> str:
    text = (objective or "").strip()
    words = len(text.split())
    multi_deliverable = len(re.findall(r"\b(y|además|también|luego|después|incluye|incluya)\b", text.lower()))
    if words >= 90 or multi_deliverable >= 4 or intent in {"research", "documents", "code"} and words >= 45:
        return "alta"
    if words >= 28 or multi_deliverable >= 2 or intent in {"research", "documents", "code", "planning"}:
        return "media"
    return "baja"


def select_professional_team(
    objective: str,
    intent: str = "general",
    complexity: str | None = None,
    max_roles: int = 5,
) -> List[ProfessionalRole]:
    normalized_intent = intent if intent in INTENT_ROLE_MAP else "general"
    complexity = complexity or infer_complexity(objective, normalized_intent)
    role_ids: List[str] = list(INTENT_ROLE_MAP[normalized_intent])
    lowered = (objective or "").lower()
    for keywords, role_id in KEYWORD_ROLES:
        if any(keyword in lowered for keyword in keywords):
            role_ids.insert(2, role_id)
    if complexity == "baja":
        role_ids = [role for role in role_ids if role not in {"writer", "project_manager"}]
    if complexity == "alta" and "auditor" not in role_ids:
        role_ids.append("auditor")
    role_ids = _unique(role_ids)
    # Director y auditor se conservan cuando existen; el resto se prioriza por el objetivo.
    limit = max(2, min(max_roles, 7))
    return [ROLE_CATALOG[role_id] for role_id in role_ids[:limit] if role_id in ROLE_CATALOG]


def build_success_criteria(objective: str, intent: str, complexity: str) -> List[str]:
    criteria = [
        "Responder completamente al objetivo y respetar el formato solicitado.",
        "Distinguir hechos, inferencias, supuestos y limitaciones.",
        "Entregar una conclusión accionable, no solo información descriptiva.",
    ]
    if intent == "research":
        criteria.extend([
            "Contrastar varias fuentes y señalar discrepancias relevantes.",
            "Indicar actualidad y calidad de la evidencia utilizada.",
        ])
    elif intent == "documents":
        criteria.extend([
            "Vincular cada hallazgo con el documento o sección correspondiente.",
            "No inventar contenido ausente en los archivos.",
        ])
    elif intent == "code":
        criteria.extend([
            "Entregar código ejecutable y cambios completos, no fragmentos inconexos.",
            "Incluir validación, manejo de errores y pruebas razonables.",
        ])
    elif intent == "math":
        criteria.extend([
            "Comprobar el cálculo por una ruta independiente cuando sea posible.",
            "Conservar unidades, precisión y condiciones del problema.",
        ])
    elif intent == "planning":
        criteria.extend([
            "Definir prioridades, dependencias, responsables y criterios de cierre.",
            "Proponer una secuencia realizable dentro de las restricciones.",
        ])
    if complexity == "alta":
        criteria.append("Guardar checkpoints y conservar resultados parciales reutilizables.")
    return criteria


def build_professional_plan(
    objective: str,
    intent: str,
    mode: str,
    project_name: str,
    confidence: float = 0.5,
    max_roles: int = 5,
) -> Dict[str, Any]:
    objective = (objective or "").strip()
    normalized_intent = intent if intent in INTENT_ROLE_MAP else "general"
    complexity = infer_complexity(objective, normalized_intent)
    team = select_professional_team(objective, normalized_intent, complexity, max_roles=max_roles)
    role_ids = [role.id for role in team]

    milestones: List[Dict[str, Any]] = [
        {
            "id": "brief",
            "name": "Definir misión",
            "owner": "director",
            "detail": "Confirmar objetivo, restricciones, entregables, audiencia y criterio de éxito.",
            "quality_gate": "El alcance es inequívoco y ejecutable.",
        }
    ]
    if "researcher" in role_ids:
        milestones.append({
            "id": "evidence",
            "name": "Construir evidencia",
            "owner": "researcher",
            "detail": "Buscar por varias rutas, depurar duplicados y conservar fuentes útiles.",
            "quality_gate": "La evidencia es relevante, diversa y suficientemente actual.",
        })
    if "analyst" in role_ids or "economist" in role_ids:
        owner = "economist" if "economist" in role_ids else "analyst"
        milestones.append({
            "id": "analysis",
            "name": "Analizar y resolver",
            "owner": owner,
            "detail": "Interpretar datos, documentos, cálculos, causas, riesgos y escenarios.",
            "quality_gate": "Los hallazgos están sustentados y no contradicen la evidencia.",
        })
    if "engineer" in role_ids:
        milestones.append({
            "id": "implementation",
            "name": "Diseñar solución técnica",
            "owner": "engineer",
            "detail": "Construir la solución completa, controlar errores y preparar pruebas.",
            "quality_gate": "La propuesta es coherente, segura y verificable.",
        })
    if "project_manager" in role_ids:
        milestones.append({
            "id": "execution",
            "name": "Organizar ejecución",
            "owner": "project_manager",
            "detail": "Definir hitos, dependencias, responsables, tiempos y seguimiento.",
            "quality_gate": "El plan puede ponerse en marcha sin ambigüedades críticas.",
        })
    if "writer" in role_ids:
        milestones.append({
            "id": "delivery",
            "name": "Preparar entregable",
            "owner": "writer",
            "detail": "Convertir los resultados en una respuesta profesional y fácil de utilizar.",
            "quality_gate": "El formato, tono y estructura responden a la necesidad del usuario.",
        })
    milestones.append({
        "id": "audit",
        "name": "Auditar resultado",
        "owner": "auditor" if "auditor" in role_ids else "director",
        "detail": "Comprobar cobertura, coherencia, cifras, riesgos, fuentes y formato final.",
        "quality_gate": "El resultado supera los criterios de calidad o declara claramente sus límites.",
    })

    target_minutes = {"baja": 3, "media": 8, "alta": 18}[complexity]
    if mode == "fast":
        target_minutes = max(2, target_minutes // 2)
    elif mode in {"research", "deep"}:
        target_minutes = int(target_minutes * 1.4)

    approval_terms = (
        "enviar", "publicar", "eliminar", "borrar", "comprar", "pagar", "transferir",
        "correo", "mensaje", "modificar base de datos", "desplegar", "commit", "pull request",
    )
    lowered = objective.lower()
    approvals = [term for term in approval_terms if term in lowered]

    return {
        "status": "planned",
        "edition": "professional",
        "objective": objective,
        "intent": normalized_intent,
        "complexity": complexity,
        "confidence": round(float(confidence or 0.5), 3),
        "mode": mode or "auto",
        "project_name": (project_name or "General")[:120],
        "team": [role.to_dict() for role in team],
        "milestones": milestones,
        "success_criteria": build_success_criteria(objective, normalized_intent, complexity),
        "requires_approval": bool(approvals),
        "approval_reasons": approvals,
        "budget": {
            "target_minutes": target_minutes,
            "max_provider_routes": 2 if complexity == "baja" else 4 if complexity == "media" else 6,
            "max_repair_cycles": 1 if complexity == "baja" else 2,
            "checkpoint_each_milestone": True,
            "independent_verification": complexity in {"media", "alta"},
        },
    }


def build_professional_execution_prompt(plan: Dict[str, Any]) -> str:
    objective = str(plan.get("objective") or "").strip()
    team = plan.get("team") or []
    milestones = plan.get("milestones") or []
    criteria = plan.get("success_criteria") or []
    team_text = "\n".join(
        f"- {member.get('name', member.get('id', 'Especialista'))}: {member.get('mission', '')}"
        for member in team
    )
    milestone_text = "\n".join(
        f"{index + 1}. {item.get('name', 'Etapa')} — responsable: {item.get('owner', 'director')}. "
        f"{item.get('detail', '')} Control: {item.get('quality_gate', '')}"
        for index, item in enumerate(milestones)
    )
    criteria_text = "\n".join(f"- {item}" for item in criteria)
    approval_text = (
        "Detente antes de ejecutar acciones externas sensibles y solicita aprobación explícita."
        if plan.get("requires_approval")
        else "Puedes ejecutar rutas internas seguras sin aprobación adicional."
    )
    return (
        "MODO PROFESIONAL JARVIS\n\n"
        f"OBJETIVO:\n{objective}\n\n"
        f"PROYECTO: {plan.get('project_name', 'General')}\n"
        f"INTENCIÓN: {plan.get('intent', 'general')}\n"
        f"COMPLEJIDAD: {plan.get('complexity', 'media')}\n\n"
        f"EQUIPO ASIGNADO:\n{team_text}\n\n"
        f"HITOS DE EJECUCIÓN:\n{milestone_text}\n\n"
        f"CRITERIOS DE ÉXITO:\n{criteria_text}\n\n"
        "REGLAS DE TRABAJO:\n"
        "- Trabaja por etapas y conserva resultados parciales útiles.\n"
        "- Usa herramientas locales o fuentes externas solo cuando aporten valor.\n"
        "- No inventes datos, archivos, fuentes ni acciones realizadas.\n"
        "- Distingue hechos, inferencias y supuestos.\n"
        "- Si una ruta falla, utiliza una alternativa razonable sin repetir indefinidamente.\n"
        "- Verifica cobertura y coherencia antes de entregar.\n"
        f"- {approval_text}\n\n"
        "ENTREGA FINAL:\n"
        "Presenta un resultado profesional, claro, accionable y completo. Incluye limitaciones reales solo cuando existan."
    )


def role_catalog_payload() -> List[Dict[str, Any]]:
    return [ROLE_CATALOG[key].to_dict() for key in ROLE_CATALOG]
