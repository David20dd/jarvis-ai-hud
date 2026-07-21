from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict


LANGUAGES = {
    "python": ("python:3.12-alpine", ["python", "/workspace/main.py"], "main.py"),
    "javascript": ("node:22-alpine", ["node", "/workspace/main.js"], "main.js"),
}


class CodeLab:
    """Opt-in Docker sandbox for small, untrusted snippets.

    The host process is never used as a fallback. If Docker isolation is not
    available, execution is refused rather than silently weakening security.
    """

    def __init__(self, enabled: bool = False, timeout_seconds: int = 12) -> None:
        self.enabled = bool(enabled)
        self.timeout_seconds = max(2, min(int(timeout_seconds), 60))
        self.docker = shutil.which("docker")

    def status(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "available": bool(self.enabled and self.docker),
            "isolation": "docker" if self.docker else "unavailable",
            "languages": sorted(LANGUAGES),
            "network": "disabled",
            "timeout_seconds": self.timeout_seconds,
            "reason": "" if self.enabled and self.docker else (
                "JARVIS_CODE_LAB_ENABLED no está activo." if not self.enabled else "Docker no está disponible en este servidor."
            ),
        }

    def run(self, language: str, code: str, *, confirmed: bool = False) -> Dict[str, Any]:
        language = (language or "").lower().strip()
        if not confirmed:
            raise PermissionError("La ejecución de código requiere confirmación explícita.")
        if not self.enabled:
            raise RuntimeError("El laboratorio de código está desactivado.")
        if not self.docker:
            raise RuntimeError("Docker no está disponible; JARVIS no ejecutará código sin aislamiento.")
        if language not in LANGUAGES:
            raise ValueError("Lenguaje no permitido. Usa python o javascript.")
        if len(code or "") > 50000:
            raise ValueError("El fragmento supera el límite de 50 000 caracteres.")
        image, command, file_name = LANGUAGES[language]
        started = time.perf_counter()
        with tempfile.TemporaryDirectory(prefix="jarvis-code-lab-") as temp_dir:
            path = Path(temp_dir) / file_name
            path.write_text(code or "", encoding="utf-8")
            mount = f"{Path(temp_dir).resolve()}:/workspace:ro"
            args = [
                self.docker, "run", "--rm", "--network", "none", "--read-only",
                "--memory", "128m", "--cpus", "0.5", "--pids-limit", "64",
                "--security-opt", "no-new-privileges", "--cap-drop", "ALL",
                "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m", "-v", mount,
                image, *command,
            ]
            env = {"PATH": os.environ.get("PATH", "")}
            try:
                result = subprocess.run(
                    args,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_seconds,
                    env=env,
                    check=False,
                )
                return {
                    "status": "completed" if result.returncode == 0 else "failed",
                    "exit_code": result.returncode,
                    "stdout": result.stdout[-20000:],
                    "stderr": result.stderr[-12000:],
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                    "isolated": True,
                }
            except subprocess.TimeoutExpired as exc:
                return {
                    "status": "timeout",
                    "exit_code": None,
                    "stdout": (exc.stdout or "")[-20000:] if isinstance(exc.stdout, str) else "",
                    "stderr": "La ejecución superó el tiempo permitido.",
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                    "isolated": True,
                }
