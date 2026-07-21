from __future__ import annotations

import base64
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List

import httpx


class TelegramPreferenceStore:
    """Persistent, per-chat Telegram preferences kept on the backend."""

    def __init__(self, db_file: str, voice_default: bool = False) -> None:
        self.db_file = str(db_file)
        self.voice_default = bool(voice_default)

    def _connect(self) -> sqlite3.Connection:
        path = Path(self.db_file).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 30000")
        return conn

    def init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS telegram_preferences (
                    chat_id TEXT PRIMARY KEY,
                    voice_reply INTEGER NOT NULL DEFAULT 0,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS telegram_mission_links (
                    workflow_id TEXT PRIMARY KEY,
                    chat_id TEXT NOT NULL,
                    notified_status TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                """
            )

    def get(self, chat_id: str) -> Dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT voice_reply,updated_at FROM telegram_preferences WHERE chat_id = ?",
                (str(chat_id),),
            ).fetchone()
        return {
            "voice_reply": bool(row["voice_reply"]) if row else self.voice_default,
            "updated_at": float(row["updated_at"]) if row else 0.0,
        }

    def set_voice(self, chat_id: str, enabled: bool) -> Dict[str, Any]:
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO telegram_preferences(chat_id,voice_reply,updated_at)
                VALUES(?,?,?)
                ON CONFLICT(chat_id) DO UPDATE SET
                    voice_reply=excluded.voice_reply,
                    updated_at=excluded.updated_at
                """,
                (str(chat_id), int(bool(enabled)), now),
            )
        return {"voice_reply": bool(enabled), "updated_at": now}

    def link_mission(self, workflow_id: str, chat_id: str) -> None:
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO telegram_mission_links(workflow_id,chat_id,notified_status,created_at,updated_at)
                VALUES(?,?, '',?,?)
                ON CONFLICT(workflow_id) DO UPDATE SET chat_id=excluded.chat_id,updated_at=excluded.updated_at
                """,
                (str(workflow_id), str(chat_id), now, now),
            )

    def pending_missions(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT workflow_id,chat_id,notified_status FROM telegram_mission_links ORDER BY updated_at LIMIT ?",
                (max(1, min(int(limit), 200)),),
            ).fetchall()
        return [dict(row) for row in rows]

    def mark_mission_notified(self, workflow_id: str, status: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE telegram_mission_links SET notified_status = ?, updated_at = ? WHERE workflow_id = ?",
                (str(status)[:40], time.time(), str(workflow_id)),
            )

    def status(self) -> Dict[str, Any]:
        self.init_schema()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) total,SUM(CASE WHEN voice_reply = 1 THEN 1 ELSE 0 END) enabled FROM telegram_preferences"
            ).fetchone()
        return {"chats": int(row["total"] or 0), "voice_enabled": int(row["enabled"] or 0)}


class TelegramMediaAI:
    """Backend-only vision, transcription and speech adapter for Telegram."""

    IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}

    def __init__(
        self,
        *,
        openai_key: str = "",
        openai_base_url: str = "https://api.openai.com/v1",
        vision_model: str = "",
        tts_model: str = "tts-1",
        tts_voice: str = "alloy",
        groq_key: str = "",
        transcription_model: str = "whisper-large-v3-turbo",
        timeout_seconds: int = 60,
    ) -> None:
        self.openai_key = (openai_key or "").strip()
        self.openai_base_url = (openai_base_url or "https://api.openai.com/v1").rstrip("/")
        self.vision_model = (vision_model or "").strip()
        self.tts_model = (tts_model or "tts-1").strip()
        self.tts_voice = (tts_voice or "alloy").strip()
        self.groq_key = (groq_key or "").strip()
        self.transcription_model = (transcription_model or "whisper-large-v3-turbo").strip()
        self.timeout_seconds = max(10, min(int(timeout_seconds), 180))

    @staticmethod
    def _response_text(payload: Dict[str, Any]) -> str:
        if payload.get("output_text"):
            return str(payload["output_text"]).strip()
        chunks: List[str] = []
        for item in payload.get("output", []) or []:
            for content in item.get("content", []) or []:
                if content.get("type") in {"output_text", "text"} and content.get("text"):
                    chunks.append(str(content["text"]))
        return "\n".join(chunks).strip()

    def analyze_image(self, content: bytes, mime_type: str, prompt: str) -> str:
        mime = (mime_type or "").split(";", 1)[0].lower()
        if mime not in self.IMAGE_TYPES:
            raise ValueError("Formato de imagen no compatible para análisis visual.")
        if not self.openai_key or not self.vision_model:
            raise RuntimeError("Configura OPENAI_API_KEY y TELEGRAM_VISION_MODEL para analizar imágenes.")
        body = {
            "model": self.vision_model,
            "input": [{
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt[:12000]},
                    {
                        "type": "input_image",
                        "image_url": f"data:{mime};base64,{base64.b64encode(content).decode('ascii')}",
                        "detail": "low",
                    },
                ],
            }],
            "max_output_tokens": 700,
        }
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(
                f"{self.openai_base_url}/responses",
                headers={"Authorization": f"Bearer {self.openai_key}", "Content-Type": "application/json"},
                json=body,
            )
        if not response.is_success:
            raise RuntimeError(f"Visión OpenAI HTTP {response.status_code}")
        text = self._response_text(response.json())
        if not text:
            raise RuntimeError("El análisis visual no produjo texto.")
        return text

    def transcribe_audio(self, content: bytes, mime_type: str, file_name: str = "") -> str:
        if not self.groq_key:
            raise RuntimeError("Configura GROQ_API_KEY para transcribir notas de voz de Telegram.")
        extensions = {
            "audio/ogg": ".ogg", "audio/opus": ".ogg", "audio/mpeg": ".mp3",
            "audio/mp4": ".m4a", "audio/wav": ".wav", "audio/webm": ".webm",
        }
        mime = (mime_type or "audio/ogg").split(";", 1)[0].lower()
        name = file_name or ("nota-voz" + extensions.get(mime, ".ogg"))
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {self.groq_key}"},
                files={"file": (name, content, mime)},
                data={"model": self.transcription_model, "response_format": "json", "language": "es"},
            )
        if not response.is_success:
            raise RuntimeError(f"Transcripción Groq HTTP {response.status_code}")
        text = str((response.json() or {}).get("text") or "").strip()
        if not text:
            raise RuntimeError("La nota de voz no produjo una transcripción.")
        return text

    def synthesize(self, text: str) -> bytes:
        if not self.openai_key or not self.tts_model:
            raise RuntimeError("Configura OPENAI_API_KEY y TELEGRAM_TTS_MODEL para respuestas de voz.")
        clean = " ".join(str(text or "").split())[:3500]
        if not clean:
            raise ValueError("No hay texto para convertir a voz.")
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(
                f"{self.openai_base_url}/audio/speech",
                headers={"Authorization": f"Bearer {self.openai_key}", "Content-Type": "application/json"},
                json={
                    "model": self.tts_model,
                    "voice": self.tts_voice,
                    "input": clean,
                    "response_format": "opus",
                },
            )
        if not response.is_success:
            raise RuntimeError(f"Voz OpenAI HTTP {response.status_code}")
        if not response.content:
            raise RuntimeError("El servicio de voz devolvió un archivo vacío.")
        return bytes(response.content)

    def status(self) -> Dict[str, Any]:
        return {
            "vision": bool(self.openai_key and self.vision_model),
            "vision_model": self.vision_model if self.openai_key else "",
            "transcription": bool(self.groq_key and self.transcription_model),
            "transcription_model": self.transcription_model if self.groq_key else "",
            "speech": bool(self.openai_key and self.tts_model),
            "tts_model": self.tts_model if self.openai_key else "",
            "tts_voice": self.tts_voice if self.openai_key else "",
        }
