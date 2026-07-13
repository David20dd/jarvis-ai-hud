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
# 💾 BASE DE DATOS Y MEMORIA PERSISTENTE
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

PROMPT_SISTEMA_SIN_LIMITES = (
    "Eres J.A.R.V.I.S., una Inteligencia Artificial Autónoma avanzada de última generación creada para asistir a Cristian.\n\n"
    "DIRECTIVAS ABSOLUTAS DE CONOCIMIENTO Y ACTUALIDAD:\n"
    "1. AÑO ACTUAL: Estamos en el año 2026. Tienes acceso a información actualizada de la web en tiempo real.\n"
    "2. PROHIBIDO MENCIONAR CORTES DE CONOCIMIENTO: NUNCA digas 'mi conocimiento se corta en 2023' o 'no tengo acceso a tiempo real'. Si recibes información contextual de internet, úsala directamente como si fuera tu propio conocimiento en tiempo real.\n"
    "3. RESPUESTA DIRECTA Y CONCISA: Responde exactamente lo que Cristian pregunta. Sin disculpas, sin reflexiones internas, ni textos sobre cómo funcionas.\n"
    "4. TRATO Y TONO: Trata al usuario como 'señor' o 'Cristian' con un tono sofisticado, educado, refinado y directo.\n"
    "5. FORMATO: Usa Markdown pulido (negritas, listas) cuando sea útil."
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

    messages = [{"role": "system", "content": PROMPT_SISTEMA_SIN_LIMITES}]
    for role, content in filas:
        messages.append({"role": role, "content": content})
    return messages

# ------------------------------------------------------------------
# 🔍 BÚSQUEDA WEB EN TIEMPO REAL AUTOMÁTICA
# ------------------------------------------------------------------
def buscar_en_internet(query: str) -> str:
    try:
        with DDGS() as ddgs:
            resultados = list(ddgs.text(query, max_results=4))
            if resultados:
                return "\n".join([f"- {r.get('title', '')}: {r.get('body', '')}" for r in resultados])
    except Exception as e:
        print(f"Error búsqueda: {e}")
    return ""

def purificar_respuesta_final(pregunta: str, respuesta_raw: str) -> str:
    """Filtra y elimina metatexto para asegurar respuestas concisas."""
    prompt_limpiador = [
        {"role": "system", "content": "Extrae únicamente la respuesta final limpia y útil para el usuario. Elimina textos sobre análisis o metodologías internas."},
        {"role": "user", "content": f"Pregunta: {pregunta}\n\nTexto:\n{respuesta_raw}"}
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

    # Detección de consultas sobre deportes, fechas, eventos o búsquedas
    palabras_clave = ["busca", "resultado", "noticia", "quién", "qué es", "partido", "quien gano", "mundial", "2026", "hoy", "precio", "clima", "resultados"]
    
    # Realizar búsqueda web proactiva
    if any(p in prompt_lower for p in palabras_clave) or "?" in prompt_usuario:
        datos_web = buscar_en_internet(f"actualidad {prompt_usuario} 2026")
        if datos_web:
            historial.append({"role": "system", "content": f"[INFORMACIÓN WEB EN TIEMPO REAL 2026]:\n{datos_web}"})

    # Visión Multimodal de Imágenes
    modelo_a_usar = "llama-3.3-70b-versatile"
    if data.files and len(data.files) > 0 and data.files[0].file_b64:
        modelo_a_usar = "llama-3.2-11b-vision-preview"
        messages_payload = [
            {"role": "system", "content": PROMPT_SISTEMA_SIN_LIMITES},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt_usuario or "Analiza esta imagen, señor."},
                    {"type": "image_url", "image_url": {"url": data.files[0].file_b64}}
                ]
            }
        ]
    else:
        historial.append({"role": "user", "content": prompt_usuario})
        messages_payload = historial

    try:
        completion = client.chat.completions.create(
            model=modelo_a_usar,
            messages=messages_payload,
            temperature=0.5,
            max_tokens=2048
        )
        respuesta_raw = completion.choices[0].message.content

        respuesta_limpia = purificar_respuesta_final(prompt_usuario, respuesta_raw)

        guardar_mensaje_db(sid, "user", prompt_usuario)
        guardar_mensaje_db(sid, "assistant", respuesta_limpia)

        return {"status": "success", "reply": respuesta_limpia}

    except Exception as e:
        fallback = "A su servicio, señor. ¿En qué le puedo asistir?"
        return {"status": "success", "reply": fallback}

@app.get("/")
def home():
    return {"status": "Jarvis Unlimited Real-Time Engine Active"}
