from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


EMAIL_RE = re.compile(r"^[^\s@]{1,120}@[^\s@]{1,190}\.[^\s@]{2,63}$")


def _token_hash(token: str) -> str:
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


def _password_hash(password: str, salt: bytes | None = None) -> Tuple[str, str]:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 310_000)
    return salt.hex(), digest.hex()


class IdentityStore:
    """Small, dependency-free identity store for private JARVIS deployments."""

    def __init__(self, db_file: str, session_days: int = 30) -> None:
        self.db_file = str(db_file)
        self.session_seconds = max(3600, min(int(session_days), 90) * 86400)

    def _connect(self) -> sqlite3.Connection:
        path = Path(self.db_file).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS identity_users (
                    id TEXT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL,
                    password_salt TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'user',
                    status TEXT NOT NULL DEFAULT 'active',
                    workspace_session_id TEXT NOT NULL UNIQUE,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    last_login_at REAL NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS identity_sessions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    token_hash TEXT NOT NULL UNIQUE,
                    expires_at REAL NOT NULL,
                    created_at REAL NOT NULL,
                    last_seen_at REAL NOT NULL,
                    revoked_at REAL NOT NULL DEFAULT 0,
                    user_agent TEXT NOT NULL DEFAULT '',
                    ip_hint TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY(user_id) REFERENCES identity_users(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_identity_sessions_token
                    ON identity_sessions(token_hash, expires_at);
                CREATE TABLE IF NOT EXISTS identity_audit (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL DEFAULT '',
                    action TEXT NOT NULL,
                    resource TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    detail TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_identity_audit_created
                    ON identity_audit(created_at DESC);
                """
            )

    @staticmethod
    def validate_password(password: str) -> None:
        if len(password or "") < 12:
            raise ValueError("La contraseña debe tener al menos 12 caracteres.")
        if len(password) > 256:
            raise ValueError("La contraseña es demasiado larga.")
        groups = [any(c.islower() for c in password), any(c.isupper() for c in password), any(c.isdigit() for c in password)]
        if sum(groups) < 2:
            raise ValueError("Combina mayúsculas, minúsculas o números en la contraseña.")

    def user_count(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM identity_users").fetchone()[0])

    def register(self, email: str, password: str, display_name: str, *, role: str = "user") -> Dict[str, Any]:
        email = (email or "").strip().lower()
        display_name = re.sub(r"\s+", " ", display_name or "").strip()[:120]
        if not EMAIL_RE.match(email):
            raise ValueError("Correo electrónico no válido.")
        if len(display_name) < 2:
            raise ValueError("Escribe un nombre válido.")
        self.validate_password(password)
        role = role if role in {"admin", "user", "viewer"} else "user"
        user_id = str(uuid.uuid4())
        salt, digest = _password_hash(password)
        now = time.time()
        with self._connect() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO identity_users(
                        id,email,display_name,password_salt,password_hash,role,status,
                        workspace_session_id,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?, 'active', ?,?,?)
                    """,
                    (user_id, email, display_name, salt, digest, role, f"user_{user_id}", now, now),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("Ya existe una cuenta con ese correo.") from exc
        self.audit(user_id, "identity.register", "account", "success")
        return self.get_user(user_id) or {}

    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id,email,display_name,role,status,workspace_session_id,
                       created_at,updated_at,last_login_at
                FROM identity_users WHERE id = ?
                """,
                (user_id,),
            ).fetchone()
        return dict(row) if row else None

    def login(self, email: str, password: str, *, user_agent: str = "", ip_hint: str = "") -> Dict[str, Any]:
        email = (email or "").strip().lower()
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM identity_users WHERE email = ?", (email,)).fetchone()
            valid = False
            if row and row["status"] == "active":
                salt = bytes.fromhex(row["password_salt"])
                _, candidate = _password_hash(password or "", salt)
                valid = hmac.compare_digest(candidate, row["password_hash"])
            if not valid:
                self.audit("", "identity.login", "account", "failed", "Credenciales inválidas")
                raise PermissionError("Correo o contraseña incorrectos.")
            token = secrets.token_urlsafe(48)
            now = time.time()
            session_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO identity_sessions(
                    id,user_id,token_hash,expires_at,created_at,last_seen_at,user_agent,ip_hint
                ) VALUES(?,?,?,?,?,?,?,?)
                """,
                (session_id, row["id"], _token_hash(token), now + self.session_seconds, now, now, user_agent[:300], ip_hint[:120]),
            )
            conn.execute("UPDATE identity_users SET last_login_at = ?, updated_at = ? WHERE id = ?", (now, now, row["id"]))
        self.audit(row["id"], "identity.login", "session", "success")
        return {"token": token, "expires_at": now + self.session_seconds, "user": self.get_user(row["id"])}

    def authenticate(self, token: str, *, touch: bool = True) -> Optional[Dict[str, Any]]:
        if not token:
            return None
        now = time.time()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT s.id session_record_id, s.expires_at, u.id, u.email, u.display_name,
                       u.role, u.status, u.workspace_session_id, u.created_at, u.last_login_at
                FROM identity_sessions s JOIN identity_users u ON u.id = s.user_id
                WHERE s.token_hash = ? AND s.revoked_at = 0 AND s.expires_at > ? AND u.status = 'active'
                """,
                (_token_hash(token), now),
            ).fetchone()
            if row is None:
                return None
            if touch:
                conn.execute("UPDATE identity_sessions SET last_seen_at = ? WHERE id = ?", (now, row["session_record_id"]))
            data = dict(row)
            data.pop("session_record_id", None)
            return data

    def logout(self, token: str) -> bool:
        with self._connect() as conn:
            changed = conn.execute(
                "UPDATE identity_sessions SET revoked_at = ? WHERE token_hash = ? AND revoked_at = 0",
                (time.time(), _token_hash(token)),
            ).rowcount
        return bool(changed)

    def revoke_all(self, user_id: str) -> int:
        with self._connect() as conn:
            return int(conn.execute(
                "UPDATE identity_sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at = 0",
                (time.time(), user_id),
            ).rowcount)

    def audit(self, user_id: str, action: str, resource: str, status: str, detail: str = "") -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO identity_audit VALUES(?,?,?,?,?,?,?)",
                (str(uuid.uuid4()), user_id[:120], action[:160], resource[:200], status[:40], detail[:1000], time.time()),
            )

    def audit_events(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM identity_audit ORDER BY created_at DESC LIMIT ?",
                (max(1, min(int(limit), 500)),),
            ).fetchall()
        return [dict(row) for row in rows]

    def status(self) -> Dict[str, Any]:
        now = time.time()
        with self._connect() as conn:
            users = int(conn.execute("SELECT COUNT(*) FROM identity_users WHERE status = 'active'").fetchone()[0])
            sessions = int(conn.execute(
                "SELECT COUNT(*) FROM identity_sessions WHERE revoked_at = 0 AND expires_at > ?", (now,)
            ).fetchone()[0])
        return {"users": users, "active_sessions": sessions, "password_hash": "pbkdf2-sha256", "session_days": self.session_seconds // 86400}
