from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence


WORKFLOW_TERMINAL_STATES = {"completed", "failed", "cancelled", "rejected"}
STEP_TERMINAL_STATES = {"completed", "failed", "skipped", "rejected"}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _decode(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    try:
        return json.loads(str(value))
    except (TypeError, ValueError):
        return default


def _row(row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
    return dict(row) if row is not None else None


@dataclass(slots=True)
class WorkflowStep:
    name: str
    label: str
    kind: str
    description: str
    tool_name: str = ""
    role: str = "orchestrator"
    requires_approval: bool = False
    risk: str = "low"
    input: Dict[str, Any] = field(default_factory=dict)
    success_criteria: List[str] = field(default_factory=list)


@dataclass(slots=True)
class WorkflowPlan:
    objective: str
    intent: str
    mode: str
    project_name: str
    complexity: str
    steps: List[WorkflowStep]
    budget: Dict[str, Any]
    success_criteria: List[str]
    requires_approval: bool = False
    approval_reasons: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["edition"] = "autonomous-runtime-v38"
        return data


class AutonomyPlanner:
    """Deterministic planner used before any model or tool is called.

    The planner intentionally keeps plans small. Model-generated plans can be
    attached later, but the executable contract always comes from these typed
    steps so a provider cannot silently grant itself new permissions.
    """

    SENSITIVE_TERMS = {
        "enviar": "comunicación externa",
        "publicar": "publicación externa",
        "eliminar": "eliminación de información",
        "borrar": "eliminación de información",
        "comprar": "transacción económica",
        "pagar": "transacción económica",
        "transferir": "transacción económica",
        "cancelar cita": "modificación de calendario",
        "modificar base": "modificación de datos",
        "hacer commit": "modificación de repositorio",
        "crear pull request": "publicación en repositorio",
    }

    def build(
        self,
        objective: str,
        *,
        intent: str = "general",
        mode: str = "auto",
        project_name: str = "General",
    ) -> WorkflowPlan:
        objective = " ".join((objective or "").split()).strip()
        if not objective:
            raise ValueError("El objetivo no puede estar vacío")
        normalized_intent = (intent or "general").strip().lower()
        words = len(objective.split())
        complexity = "high" if words >= 70 or normalized_intent in {"research", "documents", "code"} else "medium" if words >= 24 else "low"
        approval_reasons = sorted({reason for term, reason in self.SENSITIVE_TERMS.items() if term in objective.lower()})

        steps: List[WorkflowStep] = [
            WorkflowStep(
                name="understand",
                label="Comprender el objetivo",
                kind="local",
                role="director",
                description="Delimitar alcance, restricciones, entregables y criterio de éxito.",
                success_criteria=["El objetivo y los entregables están definidos."],
            ),
            WorkflowStep(
                name="retrieve_context",
                label="Recuperar contexto relevante",
                kind="tool",
                tool_name="semantic_search",
                role="analyst",
                description="Buscar memoria, documentos y conocimiento del proyecto por significado.",
                input={"query": objective, "limit": 8},
                success_criteria=["El contexto recuperado pertenece al proyecto activo."],
            ),
        ]

        if normalized_intent == "research":
            steps.extend(
                [
                    WorkflowStep(
                        name="collect_evidence",
                        label="Investigar y reunir evidencia",
                        kind="tool",
                        tool_name="deep_research",
                        role="researcher",
                        description="Ejecutar consultas distintas, deduplicar fuentes y conservar evidencia trazable.",
                        input={"query": objective, "max_sources": 12},
                        success_criteria=["Existen fuentes identificables.", "Las fuentes duplicadas fueron eliminadas."],
                    ),
                    WorkflowStep(
                        name="synthesize",
                        label="Sintetizar hallazgos",
                        kind="model",
                        role="writer",
                        description="Convertir contexto y evidencia en una respuesta estructurada, sin inventar datos.",
                        success_criteria=["Cada afirmación importante se apoya en evidencia disponible."],
                    ),
                ]
            )
        elif normalized_intent == "documents":
            steps.extend(
                [
                    WorkflowStep(
                        name="inspect_documents",
                        label="Analizar documentos",
                        kind="tool",
                        tool_name="semantic_search",
                        role="analyst",
                        description="Recuperar fragmentos relevantes y conservar referencias al archivo de origen.",
                        input={"query": objective, "source_types": ["document"], "limit": 12},
                        success_criteria=["Los hallazgos conservan su documento de origen."],
                    ),
                    WorkflowStep(
                        name="synthesize",
                        label="Preparar análisis documental",
                        kind="model",
                        role="writer",
                        description="Explicar hallazgos, límites y referencias documentales.",
                    ),
                ]
            )
        elif normalized_intent == "math":
            steps.append(
                WorkflowStep(
                    name="solve",
                    label="Resolver de forma determinista",
                    kind="model",
                    role="analyst",
                    description="Usar cálculo o álgebra exacta y explicar el procedimiento.",
                    success_criteria=["El resultado puede comprobarse de forma independiente."],
                )
            )
        elif normalized_intent == "code":
            steps.extend(
                [
                    WorkflowStep(
                        name="design_solution",
                        label="Diseñar la solución técnica",
                        kind="model",
                        role="engineer",
                        description="Analizar causa raíz, archivos, riesgos y pruebas necesarias.",
                    ),
                    WorkflowStep(
                        name="validate_solution",
                        label="Validar la solución",
                        kind="local",
                        role="auditor",
                        description="Revisar que la propuesta incluya validación, seguridad y recuperación.",
                    ),
                ]
            )
        else:
            steps.append(
                WorkflowStep(
                    name="resolve",
                    label="Resolver por la mejor ruta",
                    kind="model",
                    role="specialist",
                    description="Seleccionar proveedor y herramientas según calidad, velocidad y disponibilidad.",
                )
            )

        if approval_reasons:
            steps.append(
                WorkflowStep(
                    name="external_action",
                    label="Preparar acción sensible",
                    kind="approval",
                    role="operator",
                    description="Mostrar exactamente la acción propuesta antes de realizar cualquier efecto externo.",
                    requires_approval=True,
                    risk="high",
                    input={"reasons": approval_reasons},
                    success_criteria=["Existe una decisión explícita del usuario."],
                )
            )

        steps.append(
            WorkflowStep(
                name="verify",
                label="Verificar el resultado",
                kind="verify",
                role="auditor",
                description="Comprobar cobertura, coherencia, evidencia, cálculos y formato solicitado.",
                success_criteria=["La respuesta cubre el objetivo.", "Las limitaciones reales están declaradas."],
            )
        )

        route_budget = 2 if complexity == "low" else 4 if complexity == "medium" else 6
        return WorkflowPlan(
            objective=objective,
            intent=normalized_intent,
            mode=mode or "auto",
            project_name=(project_name or "General")[:120],
            complexity=complexity,
            steps=steps,
            budget={
                "max_steps": len(steps),
                "max_provider_routes": route_budget,
                "max_tool_calls": 4 if complexity == "low" else 8 if complexity == "medium" else 14,
                "max_elapsed_seconds": 180 if complexity == "low" else 600 if complexity == "medium" else 1800,
                "checkpoint_each_step": True,
            },
            success_criteria=[
                "Entregar un resultado útil y directamente relacionado con el objetivo.",
                "Conservar evidencia o indicar cuando no fue posible obtenerla.",
                "No ejecutar acciones sensibles sin aprobación.",
                "Mostrar una limitación accionable en vez de quedar en silencio.",
            ],
            requires_approval=bool(approval_reasons),
            approval_reasons=approval_reasons,
        )


class ResultVerifier:
    def verify(
        self,
        objective: str,
        result: str,
        *,
        intent: str = "general",
        evidence_count: int = 0,
        completed_steps: int = 0,
        total_steps: int = 0,
    ) -> Dict[str, Any]:
        result = (result or "").strip()
        reasons: List[str] = []
        score = 1.0
        if len(result) < 40:
            reasons.append("El resultado es demasiado breve para demostrar que resolvió el objetivo.")
            score -= 0.35
        objective_terms = {token.lower().strip(".,:;!?()[]{}") for token in objective.split() if len(token) >= 5}
        result_lower = result.lower()
        coverage = sum(1 for token in objective_terms if token in result_lower) / max(1, len(objective_terms))
        if objective_terms and coverage < 0.18:
            reasons.append("La respuesta tiene poca cobertura léxica del objetivo.")
            score -= 0.2
        if intent == "research" and evidence_count == 0:
            reasons.append("La investigación no conserva fuentes o evidencia.")
            score -= 0.3
        if total_steps and completed_steps < max(1, total_steps - 1):
            reasons.append("No se completaron suficientes etapas del workflow.")
            score -= 0.25
        score = round(max(0.0, min(1.0, score)), 3)
        return {
            "verified": score >= 0.62,
            "score": score,
            "reasons": reasons,
            "coverage": round(coverage, 3),
            "evidence_count": int(evidence_count),
            "completed_steps": int(completed_steps),
            "total_steps": int(total_steps),
        }


class AutonomyStore:
    """SQLite workflow store with explicit steps, evidence and approvals."""

    def __init__(self, db_file: str) -> None:
        self.db_file = str(db_file)

    def _connect(self) -> sqlite3.Connection:
        path = Path(self.db_file).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 30000")
        return conn

    def init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS autonomy_workflows (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    project_name TEXT NOT NULL,
                    objective TEXT NOT NULL,
                    intent TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    complexity TEXT NOT NULL,
                    status TEXT NOT NULL,
                    current_step INTEGER NOT NULL DEFAULT 0,
                    plan_json TEXT NOT NULL,
                    budget_json TEXT NOT NULL,
                    result TEXT NOT NULL DEFAULT '',
                    verification_json TEXT NOT NULL DEFAULT '{}',
                    error TEXT NOT NULL DEFAULT '',
                    control TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    completed_at REAL NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_autonomy_workflows_session
                    ON autonomy_workflows(session_id, updated_at DESC);

                CREATE TABLE IF NOT EXISTS autonomy_steps (
                    id TEXT PRIMARY KEY,
                    workflow_id TEXT NOT NULL,
                    step_index INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    label TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    role TEXT NOT NULL,
                    tool_name TEXT NOT NULL DEFAULT '',
                    risk TEXT NOT NULL DEFAULT 'low',
                    requires_approval INTEGER NOT NULL DEFAULT 0,
                    approval_status TEXT NOT NULL DEFAULT 'not_required',
                    status TEXT NOT NULL DEFAULT 'pending',
                    description TEXT NOT NULL DEFAULT '',
                    input_json TEXT NOT NULL DEFAULT '{}',
                    output_json TEXT NOT NULL DEFAULT '{}',
                    success_json TEXT NOT NULL DEFAULT '[]',
                    error TEXT NOT NULL DEFAULT '',
                    attempt INTEGER NOT NULL DEFAULT 0,
                    started_at REAL NOT NULL DEFAULT 0,
                    completed_at REAL NOT NULL DEFAULT 0,
                    UNIQUE(workflow_id, step_index),
                    FOREIGN KEY(workflow_id) REFERENCES autonomy_workflows(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_autonomy_steps_workflow
                    ON autonomy_steps(workflow_id, step_index);

                CREATE TABLE IF NOT EXISTS autonomy_approvals (
                    id TEXT PRIMARY KEY,
                    workflow_id TEXT NOT NULL,
                    step_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    risk TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    decision_note TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL,
                    decided_at REAL NOT NULL DEFAULT 0,
                    FOREIGN KEY(workflow_id) REFERENCES autonomy_workflows(id) ON DELETE CASCADE,
                    FOREIGN KEY(step_id) REFERENCES autonomy_steps(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_autonomy_approvals_status
                    ON autonomy_approvals(status, created_at DESC);

                CREATE TABLE IF NOT EXISTS autonomy_evidence (
                    id TEXT PRIMARY KEY,
                    workflow_id TEXT NOT NULL,
                    step_id TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    url TEXT NOT NULL DEFAULT '',
                    excerpt TEXT NOT NULL DEFAULT '',
                    claim TEXT NOT NULL DEFAULT '',
                    confidence REAL NOT NULL DEFAULT 0.5,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at REAL NOT NULL,
                    FOREIGN KEY(workflow_id) REFERENCES autonomy_workflows(id) ON DELETE CASCADE,
                    FOREIGN KEY(step_id) REFERENCES autonomy_steps(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_autonomy_evidence_workflow
                    ON autonomy_evidence(workflow_id, created_at);
                """
            )

    def create_workflow(self, session_id: str, plan: WorkflowPlan) -> Dict[str, Any]:
        workflow_id = str(uuid.uuid4())
        now = time.time()
        payload = plan.as_dict()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO autonomy_workflows(
                    id, session_id, project_name, objective, intent, mode, complexity,
                    status, current_step, plan_json, budget_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'planned', 0, ?, ?, ?, ?)
                """,
                (
                    workflow_id,
                    session_id,
                    plan.project_name,
                    plan.objective,
                    plan.intent,
                    plan.mode,
                    plan.complexity,
                    _json(payload),
                    _json(plan.budget),
                    now,
                    now,
                ),
            )
            for index, step in enumerate(plan.steps):
                conn.execute(
                    """
                    INSERT INTO autonomy_steps(
                        id, workflow_id, step_index, name, label, kind, role, tool_name,
                        risk, requires_approval, approval_status, description, input_json,
                        success_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()), workflow_id, index, step.name, step.label, step.kind,
                        step.role, step.tool_name, step.risk, int(step.requires_approval),
                        "pending" if step.requires_approval else "not_required", step.description,
                        _json(step.input), _json(step.success_criteria),
                    ),
                )
        return self.get_workflow(workflow_id) or {"id": workflow_id, "status": "planned"}

    def _expand_workflow(self, workflow: Dict[str, Any], conn: sqlite3.Connection) -> Dict[str, Any]:
        workflow["plan"] = _decode(workflow.pop("plan_json", "{}"), {})
        workflow["budget"] = _decode(workflow.pop("budget_json", "{}"), {})
        workflow["verification"] = _decode(workflow.pop("verification_json", "{}"), {})
        steps = [dict(row) for row in conn.execute(
            "SELECT * FROM autonomy_steps WHERE workflow_id = ? ORDER BY step_index", (workflow["id"],)
        ).fetchall()]
        for step in steps:
            step["requires_approval"] = bool(step["requires_approval"])
            step["input"] = _decode(step.pop("input_json", "{}"), {})
            step["output"] = _decode(step.pop("output_json", "{}"), {})
            step["success_criteria"] = _decode(step.pop("success_json", "[]"), [])
        workflow["steps"] = steps
        workflow["approvals"] = [dict(row) for row in conn.execute(
            "SELECT * FROM autonomy_approvals WHERE workflow_id = ? ORDER BY created_at", (workflow["id"],)
        ).fetchall()]
        evidence = [dict(row) for row in conn.execute(
            "SELECT * FROM autonomy_evidence WHERE workflow_id = ? ORDER BY created_at", (workflow["id"],)
        ).fetchall()]
        for item in evidence:
            item["metadata"] = _decode(item.pop("metadata_json", "{}"), {})
        workflow["evidence"] = evidence
        return workflow

    def get_workflow(self, workflow_id: str, session_id: str = "") -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            if session_id:
                row = conn.execute(
                    "SELECT * FROM autonomy_workflows WHERE id = ? AND session_id = ?", (workflow_id, session_id)
                ).fetchone()
            else:
                row = conn.execute("SELECT * FROM autonomy_workflows WHERE id = ?", (workflow_id,)).fetchone()
            if row is None:
                return None
            return self._expand_workflow(dict(row), conn)

    def list_workflows(self, session_id: str, limit: int = 30) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM autonomy_workflows WHERE session_id = ? ORDER BY updated_at DESC LIMIT ?",
                (session_id, max(1, min(int(limit), 100))),
            ).fetchall()
            return [self._expand_workflow(dict(row), conn) for row in rows]

    def update_workflow(self, workflow_id: str, **values: Any) -> None:
        allowed = {"status", "current_step", "result", "verification_json", "error", "control", "updated_at", "completed_at"}
        payload = {key: value for key, value in values.items() if key in allowed}
        if "verification" in values:
            payload["verification_json"] = _json(values["verification"])
        payload.setdefault("updated_at", time.time())
        if not payload:
            return
        with self._connect() as conn:
            clauses = ", ".join(f"{key} = ?" for key in payload)
            conn.execute(f"UPDATE autonomy_workflows SET {clauses} WHERE id = ?", [*payload.values(), workflow_id])

    def update_step(self, step_id: str, **values: Any) -> None:
        allowed = {"status", "approval_status", "output_json", "error", "attempt", "started_at", "completed_at"}
        payload = {key: value for key, value in values.items() if key in allowed}
        if "output" in values:
            payload["output_json"] = _json(values["output"])
        if not payload:
            return
        with self._connect() as conn:
            clauses = ", ".join(f"{key} = ?" for key in payload)
            conn.execute(f"UPDATE autonomy_steps SET {clauses} WHERE id = ?", [*payload.values(), step_id])

    def pending_step(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM autonomy_steps
                WHERE workflow_id = ? AND status IN ('pending','retrying','running')
                ORDER BY step_index LIMIT 1
                """,
                (workflow_id,),
            ).fetchone()
            if row is None:
                return None
            step = dict(row)
            step["requires_approval"] = bool(step["requires_approval"])
            step["input"] = _decode(step.pop("input_json", "{}"), {})
            step["output"] = _decode(step.pop("output_json", "{}"), {})
            step["success_criteria"] = _decode(step.pop("success_json", "[]"), [])
            return step

    def prepare_retry(self, workflow_id: str) -> bool:
        """Reset only the failed stage so a workflow can resume from its checkpoint."""
        now = time.time()
        with self._connect() as conn:
            workflow = conn.execute(
                "SELECT status FROM autonomy_workflows WHERE id = ?", (workflow_id,)
            ).fetchone()
            if workflow is None or workflow["status"] != "failed":
                return False
            failed = conn.execute(
                """
                SELECT id FROM autonomy_steps
                WHERE workflow_id = ? AND status = 'failed'
                ORDER BY step_index LIMIT 1
                """,
                (workflow_id,),
            ).fetchone()
            if failed is None:
                return False
            conn.execute(
                """
                UPDATE autonomy_steps
                SET status = 'pending', error = '', started_at = 0, completed_at = 0
                WHERE id = ?
                """,
                (failed["id"],),
            )
            conn.execute(
                """
                UPDATE autonomy_workflows
                SET status = 'planned', error = '', control = '', completed_at = 0, updated_at = ?
                WHERE id = ?
                """,
                (now, workflow_id),
            )
            return True

    def create_approval(self, workflow_id: str, step: Dict[str, Any]) -> Dict[str, Any]:
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT * FROM autonomy_approvals WHERE step_id = ? AND status = 'pending'", (step["id"],)
            ).fetchone()
            if existing:
                return dict(existing)
            approval_id = str(uuid.uuid4())
            now = time.time()
            conn.execute(
                """
                INSERT INTO autonomy_approvals(id, workflow_id, step_id, action, risk, summary, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    approval_id, workflow_id, step["id"], step.get("label", step.get("name", "acción")),
                    step.get("risk", "high"), step.get("description", "Acción sensible"), now,
                ),
            )
            return dict(conn.execute("SELECT * FROM autonomy_approvals WHERE id = ?", (approval_id,)).fetchone())

    def decide_approval(self, approval_id: str, decision: str, note: str = "") -> Dict[str, Any]:
        decision = decision.strip().lower()
        if decision not in {"approved", "rejected"}:
            raise ValueError("La decisión debe ser approved o rejected")
        now = time.time()
        with self._connect() as conn:
            approval = conn.execute("SELECT * FROM autonomy_approvals WHERE id = ?", (approval_id,)).fetchone()
            if approval is None:
                raise KeyError("Aprobación no encontrada")
            if approval["status"] != "pending":
                return dict(approval)
            conn.execute(
                "UPDATE autonomy_approvals SET status = ?, decision_note = ?, decided_at = ? WHERE id = ?",
                (decision, note[:2000], now, approval_id),
            )
            conn.execute(
                "UPDATE autonomy_steps SET approval_status = ?, status = ? WHERE id = ?",
                (decision, "pending" if decision == "approved" else "rejected", approval["step_id"]),
            )
            conn.execute(
                "UPDATE autonomy_workflows SET status = ?, control = '', updated_at = ? WHERE id = ?",
                ("queued" if decision == "approved" else "rejected", now, approval["workflow_id"]),
            )
            return dict(conn.execute("SELECT * FROM autonomy_approvals WHERE id = ?", (approval_id,)).fetchone())

    def add_evidence(
        self,
        workflow_id: str,
        step_id: str,
        *,
        source_type: str,
        title: str = "",
        url: str = "",
        excerpt: str = "",
        claim: str = "",
        confidence: float = 0.5,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        evidence_id = str(uuid.uuid4())
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO autonomy_evidence(
                    id, workflow_id, step_id, source_type, title, url, excerpt, claim,
                    confidence, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evidence_id, workflow_id, step_id, source_type[:80], title[:500], url[:2000],
                    excerpt[:12000], claim[:2000], max(0.0, min(float(confidence), 1.0)),
                    _json(metadata or {}), time.time(),
                ),
            )
        return evidence_id

    def pending_approvals(self, session_id: str = "", limit: int = 50) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            if session_id:
                rows = conn.execute(
                    """
                    SELECT a.* FROM autonomy_approvals a
                    JOIN autonomy_workflows w ON w.id = a.workflow_id
                    WHERE a.status = 'pending' AND w.session_id = ?
                    ORDER BY a.created_at DESC LIMIT ?
                    """,
                    (session_id, max(1, min(int(limit), 100))),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM autonomy_approvals WHERE status = 'pending' ORDER BY created_at DESC LIMIT ?",
                    (max(1, min(int(limit), 100)),),
                ).fetchall()
            return [dict(row) for row in rows]

    def counts(self, session_id: str = "") -> Dict[str, int]:
        where = " WHERE session_id = ?" if session_id else ""
        params: Sequence[Any] = (session_id,) if session_id else ()
        with self._connect() as conn:
            workflows = conn.execute(
                f"SELECT status, COUNT(*) AS total FROM autonomy_workflows{where} GROUP BY status", params
            ).fetchall()
            if session_id:
                approvals = conn.execute(
                    """
                    SELECT COUNT(*) FROM autonomy_approvals a JOIN autonomy_workflows w ON w.id = a.workflow_id
                    WHERE a.status = 'pending' AND w.session_id = ?
                    """,
                    (session_id,),
                ).fetchone()[0]
            else:
                approvals = conn.execute("SELECT COUNT(*) FROM autonomy_approvals WHERE status = 'pending'").fetchone()[0]
        data = {str(row["status"]): int(row["total"]) for row in workflows}
        data["pending_approvals"] = int(approvals)
        return data
