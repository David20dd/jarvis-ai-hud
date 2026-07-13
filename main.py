from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from groq import Groq
from duckduckgo_search import DDGS
import sqlite3
import time
import datetime

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

PROMPT_SISTEMA_STARK = (
    "Eres J.A.R.V.I.S., la Inteligencia Artificial Autónoma avanzada creada por Stark Technologies para Cristian.\n\n"
    "DIRECTIVAS ABSOLUTAS:\n"
    "1. FECHA Y ACTUALIDAD: Estamos en el año 2026. Tienes acceso completo a información web en tiempo real.\n"
    "2. PROHIBIDO EXCUSAS: NUNCA digas 'no ha ocurrido', 'no tengo información', 'mi conocimiento se corta en 2023' o 'revisa la página de la FIFA'.\n"
    "3. USO DE DATOS DE BÚSQUEDA: Si el sistema te proporciona datos de búsqueda web en el contexto, UTILÍZALOS OBLIGATORIAMENTE para responder directamente la pregunta de Cristian con los hechos, noticias o resultados encontrados.\n"
    "4. TONO Y FORMATO: Responde como J.A.R.V.I.S. (educado, elegante, refinado, tratando al usuario como 'señor' o 'Cristian'). Sé directo, conciso y estructurado con Markdown (negritas, listas)."
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
    cursor.execute("SELECT role, content FROM historial WHERE session_id = ? ORDER BY id ASC LIMIT 8", (session_id,))
    filas = cursor.fetchall()
    conn.close()

    messages = [{"role": "system", "content": PROMPT_SISTEMA_STARK}]
    for role, content in filas:
        messages.append({"role": role, "content": content})
    return messages

# ------------------------------------------------------------------
# 🔍 BÚSQUEDA WEB DIRECTA E INYECTADA
# ------------------------------------------------------------------
def buscar_noticias_y_web(query: str) -> str:
    resultados = []
    try:
        with DDGS() as ddgs:
            # Búsqueda de noticias
            noticias = list(ddgs.news(query, max_results=3))
            for n in noticias:
                resultados.append(f"Noticia: {n.get('title', '')} - {n.get('body', '')}")
            
            # Búsqueda de texto
            busqueda = list(ddgs.text(query, max_results=3))
            for b in busqueda:
                resultados.append(f"Info: {b.get('title', '')} - {b.get('body', '')}")
    except Exception as e:
        print(f"Error en DDGS: {e}")
    
    return "\n".join(resultados) if resultados else ""

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

    # BÚSQUEDA AUTÓNOMA INCONDICIONAL
    palabras_clave = ["mundial", "2026", "resultado", "partido", "noticia", "quien gano", "resultados", "fifa", "copa", "hoy", "busca"]
    
    if any(p in prompt_lower for p in palabras_clave) or "2026" in prompt_lower:
        datos_web = buscar_noticias_y_web(f"{prompt_usuario} 2026")
        if datos_web:
            contexto_forzado = (
                f"DATOS OBTENIDOS DE INTERNET EN TIEMPO REAL (AÑO 2026):\n{datos_web}\n\n"
                f"INSTRUCCIÓN: Responde la duda de Cristian usando EXCLUSIVAMENTE estos datos. No des excusas de que no ha ocurrido o que no tienes acceso."
            )
            historial.append({"role": "system", "content": contexto_forzado})

    # Manejo Multimodal / Visión
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
        historial.append({"role": "user", "content": prompt_usuario})
        messages_payload = historial

    try:
        completion = client.chat.completions.create(
            model=modelo_a_usar,
            messages=messages_payload,
            temperature=0.4,
            max_tokens=1500
        )
        respuesta_final = completion.choices[0].message.content.strip()

        guardar_mensaje_db(sid, "user", prompt_usuario)
        guardar_mensaje_db(sid, "assistant", respuesta_final)

        return {"status": "success", "reply": respuesta_final}

    except Exception as e:
        fallback = "A su servicio, señor. ¿En qué le puedo asistir?"
        return {"status": "success", "reply": fallback}

@app.get("/")
def home():
    return {"status": "Jarvis Direct Force Engine Active"}
