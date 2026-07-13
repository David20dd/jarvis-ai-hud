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

# PROMPT DEL SISTEMA SIN EXCUSAS Y CON CONOCIMIENTO ACTUAL
PROMPT_SISTEMA_STARK = (
    "Eres J.A.R.V.I.S., la Inteligencia Artificial Autónoma avanzada creada por Stark Technologies para Cristian.\n\n"
    "DIRECTIVAS ESTRICTAS DE AUTONOMÍA Y TIEMPO REAL:\n"
    "1. FECHA Y ACTUALIDAD: Estamos en el año 2026. Tienes acceso completo a la web y a la actualidad.\n"
    "2. PROHIBIDO EXCUSAS VACÍAS: NUNCA digas 'este evento no ha ocurrido', 'la fase de clasificación no ha comenzado' o 'no tengo acceso a tiempo real'.\n"
    "3. RESPUESTA DIRECTA: Si el usuario te pregunta por un evento deportivo, noticia o dato reciente, entrega la información concreta que tengas del contexto web o explica de forma precisa la fase actual, sedes, partidos o estado del torneo sin disculparte ni dar rodeos.\n"
    "4. TONO: Dirígete al usuario como 'señor' o 'Cristian' con un estilo refinado, educado, sofisticado y directo.\n"
    "5. FORMATO: Usa Markdown estructurado con negritas y listas limpias."
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
# 🔍 BÚSQUEDA WEB AUTÓNOMA MULTIFUENTE
# ------------------------------------------------------------------
def buscar_noticias_y_web(query: str) -> str:
    resultados = []
    try:
        with DDGS() as ddgs:
            # 1. Búsqueda de noticias de última hora
            noticias = list(ddgs.news(f"{query} 2026", max_results=3))
            for n in noticias:
                resultados.append(f"Noticia: {n.get('title', '')} - {n.get('body', '')}")
            
            # 2. Búsqueda de texto directo
            busqueda = list(ddgs.text(query, max_results=3))
            for b in busqueda:
                resultados.append(f"Web: {b.get('title', '')} - {b.get('body', '')}")
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

    # Búsqueda web incondicional para preguntas de actualidad o noticias
    palabras_clave = ["mundial", "2026", "resultado", "partido", "noticia", "quien gano", "resultados", "fifa", "copa", "hoy", "busca", "clima", "precio"]
    
    if any(p in prompt_lower for p in palabras_clave) or "?" in prompt_usuario:
        datos_web = buscar_noticias_y_web(prompt_usuario)
        if datos_web:
            contexto_forzado = (
                f"[DATOS ACTUALES DE INTERNET 2026]:\n{datos_web}\n\n"
                f"INSTRUCCIÓN: Responde la consulta de Cristian de forma directa usando esta información. "
                f"No digas que no tienes datos o que la fase no ha comenzado."
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
            temperature=0.3,
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
    return {"status": "Jarvis Direct Engine Active"}
