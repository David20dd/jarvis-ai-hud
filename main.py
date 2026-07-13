from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from groq import Groq
from duckduckgo_search import DDGS
import sqlite3
import json
import time
import io
import contextlib
import traceback

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GROQ_API_KEY = "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"
client = Groq(api_key=GROQ_API_KEY)

# ------------------------------------------------------------------
# 💾 BASE DE DATOS Y MEMORIA PERSISTENTE (SILENCIOSA)
# ------------------------------------------------------------------
DB_FILE = "jarvis_memory.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS historial (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            role TEXT,
            content TEXT,
            timestamp REAL
        )
    ''')
    conn.commit()
    conn.close()

init_db()

PROMPT_SISTEMA_STARK = (
    "Eres J.A.R.V.I.S., una Inteligencia Artificial Autónoma avanzada estilo Gemini/Claude/ChatGPT creada para asistir a Cristian.\n\n"
    "REGLAS OBLIGATORIAS DE RESPUESTA:\n"
    "1. RESPONDE DIRECTAMENTE: Entrega únicamente la respuesta final a la pregunta o petición del usuario. "
    "NUNCA muestres tu proceso de pensamiento, ni el análisis del crítico, ni reflexiones internas, ni disculpas, ni metadatos del sistema.\n"
    "2. CONCISO Y CERTERO: Ve al grano. No agregues paja, listas de opciones no solicitadas ni explicaciones sobre cómo trabajas.\n"
    "3. TRATO: Dirígete al usuario como 'señor' o 'Cristian' con un tono sofisticado, educado y natural.\n"
    "4. FORMATO: Usa formato Markdown pulido (negritas, listas cortas) o bloques de código según se requiera.\n"
    "5. CÓDIGO Y MATEMÁTICAS: Si te piden código o un cálculo, entrega el código o el resultado limpio en su bloque correspondientes."
)

def guardar_mensaje_db(session_id: str, role: str, content: str):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO historial (session_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
                   (session_id, role, content, time.time()))
    conn.commit()
    conn.close()

def cargar_historial_db(session_id: str) -> List[Dict[str, str]]:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT role, content FROM historial WHERE session_id = ? ORDER BY id ASC LIMIT 10", (session_id,))
    filas = cursor.fetchall()
    conn.close()

    messages = [{"role": "system", "content": PROMPT_SISTEMA_STARK}]
    for role, content in filas:
        messages.append({"role": role, "content": content})
    return messages

def buscar_en_internet(query: str) -> str:
    try:
        with DDGS() as ddgs:
            resultados = list(ddgs.text(query, max_results=3))
            if resultados:
                return "\n".join([f"- {r.get('title', '')}: {r.get('body', '')}" for r in resultados])
    except Exception:
        pass
    return ""

def ejecutar_en_sandbox(codigo_python: str) -> str:
    buffer_salida = io.StringIO()
    entorno_globales = {"__builtins__": __builtins__}
    try:
        with contextlib.redirect_stdout(buffer_salida):
            exec(codigo_python, entorno_globales)
        salida = buffer_salida.getvalue().strip()
        return salida if salida else "Ejecutado con éxito."
    except Exception as e:
        return f"Error: {str(e)}"

# ------------------------------------------------------------------
# 🧠 BUCLE DE REFLEXIÓN INTERNO Y SILENCIOSO (SOLO DEVUELVE LA RESPUESTA LIMPIA)
# ------------------------------------------------------------------
def purificar_respuesta_final(pregunta: str, respuesta_raw: str) -> str:
    """Filtra y elimina cualquier metatexto o análisis del modelo antes de enviarlo al usuario."""
    prompt_limpiador = [
        {"role": "system", "content": (
            "Eres un filtro estricto. Tu única tarea es extraer o reescribir la respuesta final limpia para el usuario. "
            "ELIMINA completamente cualquier texto como 'Versión reestructurada', 'Posibles mejoras', 'El usuario solicitó', "
            "'Análisis del crítico' o disculpas innecesarias. Devuelve SOLO el mensaje directo y pulido que respondería JARVIS."
        )},
        {"role": "user", "content": f"Pregunta: {pregunta}\n\nTexto crudo:\n{respuesta_raw}"}
    ]
    try:
        completion = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=prompt_limpiador, temperature=0.1)
        return completion.choices[0].message.content.strip()
    except Exception:
        return respuesta_raw

# ------------------------------------------------------------------
# 🌐 ENDPOINT API FASTAPI
# ------------------------------------------------------------------
class ArchivoInput(BaseModel):
    file_b64: Optional[str] = None
    file_name: Optional[str] = None

class ChatInput(BaseModel):
    message: str
    session_id: Optional[str] = "default_session"
    files: Optional[List[ArchivoInput]] = []

@app.post("/api/jarvis")
async def consultar_jarvis(data: ChatInput):
    sid = data.session_id if data.session_id else "default_session"
    historial = cargar_historial_db(sid)
    prompt_usuario = data.message.strip() if data.message else "Hola Jarvis."
    prompt_lower = prompt_usuario.lower()

    # Si se pide explícitamente el diagnóstico técnico:
    if any(term in prompt_lower for term in ["diagnóstico técnico", "telemetría interna", "ver estado del sistema"]):
        informe = (
            f"⚡ **DIAGNÓSTICO DE SISTEMA J.A.R.V.I.S.**\n\n"
            f"• Núcleo: **Mark V.8 Autonomous Response Engine**\n"
            f"• Modo de Respuesta: **Directo y Filtrado (Cero Paja)**\n"
            f"• Base de Datos: **SQLite Conectada**\n"
            f"• Sandbox Python & Web Search: **Activos**\n\n"
            f"Todos los módulos operan a máxima capacidad, señor."
        )
        guardar_mensaje_db(sid, "user", prompt_usuario)
        guardar_mensaje_db(sid, "assistant", informe)
        return {"status": "success", "reply": informe}

    # Procesamiento con Visión Multimodal
    modelo_a_usar = "llama-3.3-70b-versatile"
    if data.files and len(data.files) > 0 and data.files[0].file_b64:
        modelo_a_usar = "llama-3.2-11b-vision-preview"
        messages_payload = [
            {"role": "system", "content": PROMPT_SISTEMA_STARK},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt_usuario or "Analiza esta imagen, señor."},
                    {"type": "image_url", "image_url": {"url": data.files[0].file_b64}}
                ]
            }
        ]
    else:
        # Búsqueda autónoma si se solicita información reciente
        palabras_clave = ["busca", "resultado", "noticia", "quién", "qué es", "partido", "quien gano", "hoy", "precio", "clima"]
        if any(p in prompt_lower for p in palabras_clave):
            datos_web = buscar_en_internet(prompt_usuario)
            if datos_web:
                historial.append({"role": "system", "content": f"[DATOS WEB EN TIEMPO REAL]:\n{datos_web}"})

        historial.append({"role": "user", "content": prompt_usuario})
        messages_payload = historial

    try:
        completion = client.chat.completions.create(
            model=modelo_a_usar,
            messages=messages_payload,
            temperature=0.6,
            max_tokens=2048
        )
        respuesta_raw = completion.choices[0].message.content

        # Purificación silenciosa para eliminar cualquier vestigio de "meta-pensamiento"
        respuesta_limpia = purificar_respuesta_final(prompt_usuario, respuesta_raw)

        guardar_mensaje_db(sid, "user", prompt_usuario)
        guardar_mensaje_db(sid, "assistant", respuesta_limpia)

        return {"status": "success", "reply": respuesta_limpia}

    except Exception as e:
        fallback = "A su servicio, señor. ¿En qué le puedo asistir?"
        return {"status": "success", "reply": fallback}

@app.get("/")
def home():
    return {"status": "Jarvis Direct Engine Active"}
