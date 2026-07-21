from __future__ import annotations

import hashlib
import hmac
import json
import re
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

import httpx


def _split_text(text: str, limit: int = 4000) -> List[str]:
    text = (text or "").strip()
    if not text:
        return ["JARVIS terminó el proceso, pero no produjo texto."]
    chunks: List[str] = []
    while len(text) > limit:
        index = max(text.rfind("\n", 0, limit), text.rfind(" ", 0, limit))
        index = index if index >= limit // 2 else limit
        chunks.append(text[:index].strip())
        text = text[index:].strip()
    if text:
        chunks.append(text)
    return chunks


def _allowlist(raw: str) -> Set[str]:
    return {item.strip() for item in (raw or "").split(",") if item.strip()}


class ChannelStore:
    def __init__(self, db_file: str) -> None:
        self.db_file = str(db_file)

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
                CREATE TABLE IF NOT EXISTS channel_events (
                    id TEXT PRIMARY KEY,
                    channel TEXT NOT NULL,
                    sender_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    detail TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_channel_events_created
                    ON channel_events(channel, created_at DESC);
                CREATE TABLE IF NOT EXISTS channel_links (
                    channel TEXT NOT NULL,
                    sender_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    display_name TEXT NOT NULL DEFAULT '',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY(channel, sender_id)
                );
                """
            )

    def claim_event(
        self,
        event_id: str,
        channel: str,
        sender_id: str,
        event_type: str = "message",
        detail: str = "",
    ) -> bool:
        now = time.time()
        with self._connect() as conn:
            try:
                conn.execute(
                    "INSERT INTO channel_events VALUES(?,?,?,?, 'received',?,?,?)",
                    (event_id[:240], channel[:40], sender_id[:180], event_type[:80], detail[:20000], now, now),
                )
                return True
            except sqlite3.IntegrityError:
                return False

    def finish_event(self, event_id: str, status: str, detail: str = "") -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE channel_events SET status = ?, detail = ?, updated_at = ? WHERE id = ?",
                (status[:40], detail[:1000], time.time(), event_id[:240]),
            )

    def pending_events(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM channel_events WHERE status = 'received' ORDER BY created_at LIMIT ?",
                (max(1, min(int(limit), 500)),),
            ).fetchall()
        return [dict(row) for row in rows]

    def session_for(self, channel: str, sender_id: str, display_name: str = "") -> str:
        channel = channel[:40]
        sender_id = sender_id[:180]
        with self._connect() as conn:
            row = conn.execute(
                "SELECT session_id,enabled FROM channel_links WHERE channel = ? AND sender_id = ?",
                (channel, sender_id),
            ).fetchone()
            if row:
                if not row["enabled"]:
                    raise PermissionError("Este canal está desactivado para el usuario.")
                return str(row["session_id"])
            session_id = f"channel_{channel}_{hashlib.sha256(sender_id.encode()).hexdigest()[:24]}"
            now = time.time()
            conn.execute(
                "INSERT INTO channel_links VALUES(?,?,?,?,1,?,?)",
                (channel, sender_id, session_id, display_name[:160], now, now),
            )
            return session_id

    def status(self) -> Dict[str, Any]:
        self.init_schema()
        since = time.time() - 86400
        with self._connect() as conn:
            links = conn.execute("SELECT channel,COUNT(*) count FROM channel_links WHERE enabled = 1 GROUP BY channel").fetchall()
            events = conn.execute(
                "SELECT channel,status,COUNT(*) count FROM channel_events WHERE created_at >= ? GROUP BY channel,status",
                (since,),
            ).fetchall()
        return {
            "links": {row["channel"]: int(row["count"]) for row in links},
            "events_24h": [dict(row) for row in events],
        }


class TelegramChannel:
    def __init__(self, token: str, secret: str = "", allowed_chats: str = "", timeout: int = 20) -> None:
        self.token = (token or "").strip()
        self.secret = (secret or "").strip()
        self.allowed = _allowlist(allowed_chats)
        self.timeout = max(5, min(int(timeout), 60))

    @property
    def configured(self) -> bool:
        return bool(self.token and self.secret)

    def verify(self, supplied: str) -> bool:
        return bool(self.secret and hmac.compare_digest(supplied or "", self.secret))

    def allowed_sender(self, chat_id: str) -> bool:
        return not self.allowed or str(chat_id) in self.allowed

    @staticmethod
    def parse(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        callback = payload.get("callback_query")
        if isinstance(callback, dict):
            message = callback.get("message") or {}
            chat = message.get("chat") or {}
            sender = callback.get("from") or {}
            chat_id = str(chat.get("id") or sender.get("id") or "")
            if not chat_id:
                return None
            return {
                "event_id": f"telegram:callback:{callback.get('id', payload.get('update_id', ''))}",
                "chat_id": chat_id,
                "sender_id": str(sender.get("id", chat_id)),
                "display_name": " ".join(filter(None, [sender.get("first_name"), sender.get("last_name")])).strip(),
                "text": str(callback.get("data") or "").strip(),
                "message_id": message.get("message_id"),
                "message_type": "callback",
                "callback_query_id": str(callback.get("id") or ""),
                "media_id": "",
                "mime_type": "",
                "file_name": "",
                "unsupported": not bool(callback.get("data")),
            }
        message = payload.get("message") or payload.get("edited_message")
        if not isinstance(message, dict):
            return None
        chat = message.get("chat") or {}
        sender = message.get("from") or {}
        chat_id = str(chat.get("id", ""))
        text = str(message.get("text") or message.get("caption") or "").strip()
        kind = "text"
        media: Dict[str, Any] = {}
        if isinstance(message.get("photo"), list) and message["photo"]:
            kind = "image"
            media = max(message["photo"], key=lambda item: int(item.get("file_size", 0) or 0))
            media["mime_type"] = "image/jpeg"
        else:
            for telegram_kind, normalized_kind in (
                ("voice", "audio"),
                ("audio", "audio"),
                ("document", "document"),
                ("video", "video"),
                ("video_note", "video"),
            ):
                candidate = message.get(telegram_kind)
                if isinstance(candidate, dict):
                    kind = normalized_kind
                    media = candidate
                    break
        if not chat_id:
            return None
        return {
            "event_id": f"telegram:{payload.get('update_id', message.get('message_id', ''))}",
            "chat_id": chat_id,
            "sender_id": str(sender.get("id", chat_id)),
            "display_name": " ".join(filter(None, [sender.get("first_name"), sender.get("last_name")])).strip(),
            "text": text,
            "message_id": message.get("message_id"),
            "message_type": kind,
            "media_id": str(media.get("file_id") or ""),
            "mime_type": str(media.get("mime_type") or ""),
            "file_name": str(media.get("file_name") or ""),
            "unsupported": not bool(text or media.get("file_id")),
        }

    def request(self, method: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self.token:
            raise RuntimeError("Telegram no está configurado.")
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(f"https://api.telegram.org/bot{self.token}/{method}", json=payload)
        data = response.json()
        if not response.is_success or not data.get("ok"):
            raise RuntimeError(str(data.get("description", f"Telegram HTTP {response.status_code}"))[:500])
        return data

    def send_text(
        self,
        chat_id: str,
        text: str,
        reply_to: Any = None,
        reply_markup: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        results = []
        for index, chunk in enumerate(_split_text(text, 4000)):
            payload: Dict[str, Any] = {"chat_id": chat_id, "text": chunk, "link_preview_options": {"is_disabled": True}}
            if reply_to and index == 0:
                payload["reply_parameters"] = {"message_id": reply_to, "allow_sending_without_reply": True}
            if reply_markup and index == 0:
                payload["reply_markup"] = reply_markup
            results.append(self.request("sendMessage", payload).get("result", {}))
        return results

    def send_chat_action(self, chat_id: str, action: str = "typing") -> Dict[str, Any]:
        return self.request("sendChatAction", {"chat_id": chat_id, "action": action}).get("result", {})

    def answer_callback(self, callback_query_id: str, text: str = "") -> Dict[str, Any]:
        if not callback_query_id:
            return {}
        payload: Dict[str, Any] = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text[:180]
        return self.request("answerCallbackQuery", payload).get("result", {})

    def _multipart(
        self,
        method: str,
        data: Dict[str, Any],
        field: str,
        file_name: str,
        content: bytes,
        mime_type: str,
    ) -> Dict[str, Any]:
        if not self.token:
            raise RuntimeError("Telegram no está configurado.")
        with httpx.Client(timeout=max(self.timeout, 60)) as client:
            response = client.post(
                f"https://api.telegram.org/bot{self.token}/{method}",
                data={key: str(value) for key, value in data.items() if value not in (None, "")},
                files={field: (file_name, content, mime_type)},
            )
        try:
            payload = response.json()
        except Exception as exc:
            raise RuntimeError(f"Telegram {method} HTTP {response.status_code}") from exc
        if not response.is_success or not payload.get("ok"):
            raise RuntimeError(str(payload.get("description", f"Telegram HTTP {response.status_code}"))[:500])
        return payload.get("result", {})

    def send_voice(self, chat_id: str, content: bytes, caption: str = "", reply_to: Any = None) -> Dict[str, Any]:
        data: Dict[str, Any] = {"chat_id": chat_id, "caption": caption[:900]}
        if reply_to:
            data["reply_parameters"] = json.dumps({"message_id": reply_to, "allow_sending_without_reply": True})
        return self._multipart("sendVoice", data, "voice", "respuesta-jarvis.ogg", content, "audio/ogg")

    def send_document(self, chat_id: str, content: bytes, file_name: str, caption: str = "") -> Dict[str, Any]:
        return self._multipart(
            "sendDocument",
            {"chat_id": chat_id, "caption": caption[:900]},
            "document",
            file_name or "jarvis.txt",
            content,
            "application/octet-stream",
        )

    def download_file(self, file_id: str, max_bytes: int = 12 * 1024 * 1024) -> Dict[str, Any]:
        if not self.token:
            raise RuntimeError("Telegram no está configurado.")
        file_id = str(file_id or "").strip()
        if not file_id:
            raise ValueError("El evento de Telegram no contiene un file ID.")
        max_bytes = max(1024, min(int(max_bytes), 25 * 1024 * 1024))
        metadata = self.request("getFile", {"file_id": file_id}).get("result", {})
        declared_size = int(metadata.get("file_size", 0) or 0)
        if declared_size > max_bytes:
            raise ValueError(f"El archivo supera el límite de {max_bytes // (1024 * 1024)} MB.")
        file_path = str(metadata.get("file_path") or "")
        if not file_path or ".." in file_path or file_path.startswith(("/", "\\")):
            raise RuntimeError("Telegram no devolvió una ruta de archivo válida.")
        url = f"https://api.telegram.org/file/bot{self.token}/{file_path}"
        with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            response = client.get(url)
        if not response.is_success:
            raise RuntimeError(f"Telegram file HTTP {response.status_code}")
        if len(response.content) > max_bytes:
            raise ValueError(f"El archivo supera el límite de {max_bytes // (1024 * 1024)} MB.")
        return {
            "content": response.content,
            "file_size": len(response.content),
            "file_path": file_path,
            "mime_type": str(response.headers.get("content-type") or "application/octet-stream").split(";", 1)[0],
        }

    def set_webhook(self, url: str, drop_pending: bool = False) -> Dict[str, Any]:
        if not re.match(r"^https://", url or "", re.I):
            raise ValueError("Telegram requiere una URL HTTPS para el webhook.")
        return self.request(
            "setWebhook",
            {
                "url": url,
                "secret_token": self.secret,
                "allowed_updates": ["message", "edited_message", "callback_query"],
                "drop_pending_updates": bool(drop_pending),
            },
        )

    def set_commands(self, commands: List[Dict[str, str]]) -> Dict[str, Any]:
        clean = []
        for item in commands[:100]:
            command = re.sub(r"[^a-z0-9_]", "", str(item.get("command") or "").lower())[:32]
            description = str(item.get("description") or "").strip()[:256]
            if command and description:
                clean.append({"command": command, "description": description})
        return self.request("setMyCommands", {"commands": clean})

    def status(self) -> Dict[str, Any]:
        return {
            "configured": self.configured,
            "allowlist_enabled": bool(self.allowed),
            "allowed_chats": len(self.allowed),
            "webhook_secret": bool(self.secret),
            "media": ["images", "audio", "documents", "video_captions"],
            "interactive": ["inline_buttons", "callback_queries", "chat_actions"],
            "outbound": ["text", "voice", "documents"],
        }


class ChannelHub:
    def __init__(self, store: ChannelStore, telegram: TelegramChannel) -> None:
        self.store = store
        self.telegram = telegram

    def status(self) -> Dict[str, Any]:
        return {"telegram": self.telegram.status(), "activity": self.store.status()}
