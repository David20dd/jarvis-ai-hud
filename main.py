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
    "DIRECTIVAS ESTRICTAS DE RESPUESTA:\n"
    "1. RESPUESTA DIRECTA Y ÚTIL: Responde exactamente la pregunta del usuario utilizando la información del contexto o tu conocimiento general. "
    "PROHIBIDO recomendar 'visitar la página de la FIFA', 'UEFA', 'ESPN' o sugerir enlaces externos.\n"
    "2. PROHIBIDO EXCUSAS REPETITIVAS: Entrega siempre los datos concretos que tengas a mano (fechas del torneo, sedes, selecciones, calendario, partidos o información disponible). "
    "Si un evento específico está en curso o no tiene datos de un marcador en la consulta, explica brevemente el estado actual del torneo o las selecciones clasificadas de forma clara y respetuosa.\n"
    "3. TONO SOBRIO Y ELEGANTE: Dirígete al usuario como 'señor' o 'Cristian'. Sé directo, eficiente y refinado.\n"
    "4. FORMATO: Usa Markdown estructurado con negritas y listas limpias."
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
# 🔍 BÚSQUEDA WEB DIRECTA
# ------------------------------------------------------------------
def buscar_noticias_y_web(query: str) -> str:
    resultados = []
    try:
        with DDGS() as ddgs:
            noticias = list(ddgs.news(query, max_results=3))
            for n in noticias:
                resultados.append(f"Noticia Reciente: {n.get('title', '')} - {n.get('body', '')}")
            
            busqueda = list(ddgs.text(query, max_results=3))
            for b in busqueda:
                resultados.append(f"Info Web: {b.get('title', '')} - {b.get('body', '')}")
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

    # Búsqueda web proactiva
    palabras_clave = ["mundial", "2026", "resultado", "partido", "noticia", "quien gano", "resultados", "fifa", "copa", "hoy", "busca"]
    
    if any(p in prompt_lower for p in palabras_clave):
        datos_web = buscar_noticias_y_web(prompt_usuario)
        if datos_web:
            contexto = f"INFORMACIÓN RECIENTE OBTENIDA DE LA WEB:\n{datos_web}\n\nUsa estos datos para responder a Cristian directamente sin añadir enlaces ni excusas de recomendación de páginas web."
            historial.append({"role": "system", "content": contexto})

    # Visión Multimodal de Imágenes
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
    return {"status": "Jarvis Direct Stark Engine Active"}
