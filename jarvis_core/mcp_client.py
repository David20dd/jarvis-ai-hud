from __future__ import annotations

import json
import re
import threading
import uuid
from typing import Any, Dict, List, Optional

import httpx


SAFE_NAME = re.compile(r"^[a-zA-Z0-9_.-]{1,120}$")


class MCPError(RuntimeError):
    pass


class MCPHttpServer:
    def __init__(self, name: str, url: str, headers: Optional[Dict[str, str]] = None, timeout: int = 20) -> None:
        if not SAFE_NAME.match(name or ""):
            raise ValueError("Nombre MCP no válido")
        if not str(url).startswith(("https://", "http://127.0.0.1", "http://localhost")):
            raise ValueError("El servidor MCP debe usar HTTPS o localhost")
        self.name = name
        self.url = str(url).rstrip("/")
        self.headers = {str(k): str(v) for k, v in (headers or {}).items()}
        self.timeout = max(5, min(int(timeout), 90))
        self.session_id = ""
        self.initialized = False
        self._lock = threading.RLock()
        self._counter = 0

    def _id(self) -> int:
        self._counter += 1
        return self._counter

    @staticmethod
    def _decode(response: httpx.Response) -> Dict[str, Any]:
        content_type = response.headers.get("content-type", "").lower()
        if "text/event-stream" in content_type:
            for line in reversed(response.text.splitlines()):
                if line.startswith("data:"):
                    value = line[5:].strip()
                    if value and value != "[DONE]":
                        return json.loads(value)
            raise MCPError("El servidor MCP devolvió un stream vacío")
        return response.json()

    def _request(self, method: str, params: Optional[Dict[str, Any]] = None, notification: bool = False) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        if not notification:
            payload["id"] = self._id()
        headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json", **self.headers}
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            response = client.post(self.url, headers=headers, json=payload)
        response.raise_for_status()
        if response.headers.get("Mcp-Session-Id"):
            self.session_id = response.headers["Mcp-Session-Id"]
        if notification and not response.content:
            return {}
        data = self._decode(response)
        if data.get("error"):
            error = data["error"]
            raise MCPError(str(error.get("message", error))[:600])
        return data.get("result", data)

    def initialize(self) -> Dict[str, Any]:
        with self._lock:
            if self.initialized:
                return {"initialized": True, "session_id": bool(self.session_id)}
            result = self._request(
                "initialize",
                {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "jarvis-v38", "version": "38.0.0"},
                },
            )
            self._request("notifications/initialized", notification=True)
            self.initialized = True
            return result

    def list_tools(self) -> List[Dict[str, Any]]:
        self.initialize()
        result = self._request("tools/list", {})
        return list(result.get("tools", []))

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if not SAFE_NAME.match(tool_name or ""):
            raise ValueError("Nombre de herramienta MCP no válido")
        self.initialize()
        return self._request("tools/call", {"name": tool_name, "arguments": arguments or {}})


class MCPManager:
    """Optional allowlisted MCP client configured only from backend env JSON."""

    def __init__(self, raw_config: str = "") -> None:
        self.servers: Dict[str, MCPHttpServer] = {}
        self.errors: List[str] = []
        if not (raw_config or "").strip():
            return
        try:
            config = json.loads(raw_config)
            for item in config if isinstance(config, list) else []:
                server = MCPHttpServer(
                    str(item.get("name", "")),
                    str(item.get("url", "")),
                    headers=item.get("headers") if isinstance(item.get("headers"), dict) else {},
                    timeout=int(item.get("timeout", 20)),
                )
                self.servers[server.name] = server
        except Exception as exc:
            self.errors.append(f"Configuración MCP inválida: {type(exc).__name__}: {exc}"[:600])

    @property
    def configured(self) -> bool:
        return bool(self.servers)

    def status(self, discover: bool = False) -> Dict[str, Any]:
        rows = []
        for name, server in self.servers.items():
            row: Dict[str, Any] = {"name": name, "url": server.url, "initialized": server.initialized, "status": "configured"}
            if discover:
                try:
                    tools = server.list_tools()
                    row.update({"status": "ready", "tool_count": len(tools), "tools": tools})
                except Exception as exc:
                    row.update({"status": "unavailable", "detail": f"{type(exc).__name__}: {exc}"[:300]})
            rows.append(row)
        return {"configured": self.configured, "servers": rows, "errors": self.errors}

    def call(self, server_name: str, tool_name: str, arguments: Dict[str, Any], *, confirmed: bool = False) -> Dict[str, Any]:
        if not confirmed:
            raise PermissionError("Las herramientas MCP requieren confirmación explícita.")
        server = self.servers.get(server_name)
        if not server:
            raise KeyError("Servidor MCP no configurado")
        call_id = str(uuid.uuid4())
        return {"call_id": call_id, "server": server_name, "tool": tool_name, "result": server.call_tool(tool_name, arguments)}
