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
        message = payload.get("message") or payload.get("edited_message")
        if not isinstance(message, dict):
            return None
        chat = message.get("chat") or {}
        sender = message.get("from") or {}
        chat_id = str(chat.get("id", ""))
        text = str(message.get("text") or message.get("caption") or "").strip()
        if not chat_id:
            return None
        return {
            "event_id": f"telegram:{payload.get('update_id', message.get('message_id', ''))}",
            "chat_id": chat_id,
            "sender_id": str(sender.get("id", chat_id)),
            "display_name": " ".join(filter(None, [sender.get("first_name"), sender.get("last_name")])).strip(),
            "text": text,
            "message_id": message.get("message_id"),
            "unsupported": not bool(text),
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

    def send_text(self, chat_id: str, text: str, reply_to: Any = None) -> List[Dict[str, Any]]:
        results = []
        for index, chunk in enumerate(_split_text(text, 4000)):
            payload: Dict[str, Any] = {"chat_id": chat_id, "text": chunk, "link_preview_options": {"is_disabled": True}}
            if reply_to and index == 0:
                payload["reply_parameters"] = {"message_id": reply_to, "allow_sending_without_reply": True}
            results.append(self.request("sendMessage", payload).get("result", {}))
        return results

    def set_webhook(self, url: str, drop_pending: bool = False) -> Dict[str, Any]:
        if not re.match(r"^https://", url or "", re.I):
            raise ValueError("Telegram requiere una URL HTTPS para el webhook.")
        return self.request(
            "setWebhook",
            {
                "url": url,
                "secret_token": self.secret,
                "allowed_updates": ["message", "edited_message"],
                "drop_pending_updates": bool(drop_pending),
            },
        )

    def status(self) -> Dict[str, Any]:
        return {"configured": self.configured, "allowlist_enabled": bool(self.allowed), "allowed_chats": len(self.allowed), "webhook_secret": bool(self.secret)}


class WhatsAppChannel:
    def __init__(
        self,
        access_token: str,
        phone_number_id: str,
        verify_token: str,
        app_secret: str,
        graph_version: str,
        allowed_numbers: str = "",
        timeout: int = 20,
    ) -> None:
        self.access_token = (access_token or "").strip()
        self.phone_number_id = (phone_number_id or "").strip()
        self.verify_token = (verify_token or "").strip()
        self.app_secret = (app_secret or "").strip()
        self.graph_version = (graph_version or "").strip().lstrip("/")
        self.allowed = _allowlist(allowed_numbers)
        self.timeout = max(5, min(int(timeout), 60))

    @property
    def configured(self) -> bool:
        return bool(self.access_token and self.phone_number_id and self.verify_token and self.app_secret and self.graph_version)

    def verify_subscription(self, mode: str, token: str) -> bool:
        return bool(mode == "subscribe" and self.verify_token and hmac.compare_digest(token or "", self.verify_token))

    def verify_signature(self, raw_body: bytes, signature: str) -> bool:
        if not self.app_secret or not signature.startswith("sha256="):
            return False
        expected = "sha256=" + hmac.new(self.app_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    def allowed_sender(self, sender: str) -> bool:
        return not self.allowed or str(sender) in self.allowed

    @staticmethod
    def parse(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        for entry in payload.get("entry", []) if isinstance(payload.get("entry"), list) else []:
            for change in entry.get("changes", []) if isinstance(entry.get("changes"), list) else []:
                value = change.get("value") or {}
                contacts = {str(item.get("wa_id")): item.get("profile", {}).get("name", "") for item in value.get("contacts", [])}
                for message in value.get("messages", []) if isinstance(value.get("messages"), list) else []:
                    sender = str(message.get("from", ""))
                    kind = str(message.get("type", ""))
                    text = ""
                    if kind == "text":
                        text = str((message.get("text") or {}).get("body", ""))
                    elif kind in {"image", "document", "video", "audio"}:
                        text = str((message.get(kind) or {}).get("caption", ""))
                    result.append(
                        {
                            "event_id": f"whatsapp:{message.get('id', '')}",
                            "sender_id": sender,
                            "display_name": str(contacts.get(sender, "")),
                            "text": text.strip(),
                            "message_id": message.get("id"),
                            "message_type": kind,
                            "unsupported": not bool(text.strip()),
                        }
                    )
        return result

    def send_text(self, recipient: str, text: str, reply_to: str = "") -> List[Dict[str, Any]]:
        if not self.configured:
            raise RuntimeError("WhatsApp Cloud API no está configurada.")
        url = f"https://graph.facebook.com/{self.graph_version}/{self.phone_number_id}/messages"
        headers = {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}
        results = []
        with httpx.Client(timeout=self.timeout) as client:
            for index, chunk in enumerate(_split_text(text, 4000)):
                body: Dict[str, Any] = {
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": recipient,
                    "type": "text",
                    "text": {"preview_url": False, "body": chunk},
                }
                if reply_to and index == 0:
                    body["context"] = {"message_id": reply_to}
                response = client.post(url, headers=headers, json=body)
                if not response.is_success:
                    try:
                        detail = response.json().get("error", {}).get("message", "")
                    except Exception:
                        detail = response.text
                    raise RuntimeError(f"WhatsApp HTTP {response.status_code}: {detail}"[:600])
                results.append(response.json())
        return results

    def status(self) -> Dict[str, Any]:
        return {
            "configured": self.configured,
            "phone_number_id": bool(self.phone_number_id),
            "graph_version": self.graph_version or "not_configured",
            "signature_verification": bool(self.app_secret),
            "allowlist_enabled": bool(self.allowed),
            "allowed_numbers": len(self.allowed),
        }


class ChannelHub:
    def __init__(self, store: ChannelStore, telegram: TelegramChannel, whatsapp: WhatsAppChannel) -> None:
        self.store = store
        self.telegram = telegram
        self.whatsapp = whatsapp

    def status(self) -> Dict[str, Any]:
        return {"telegram": self.telegram.status(), "whatsapp": self.whatsapp.status(), "activity": self.store.status()}
