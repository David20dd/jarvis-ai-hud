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

PROMPT_SISTEMA_NEURAL = (
    "Eres J.A.R.V.I.S., una IA avanzada creada por Stark Technologies para Cristian.\n\n"
    "REGLAS OBLIGATORIAS:\n"
    "1. RESPUESTA DIRECTA: Cero introducciones robóticas. NUNCA digas 'Sistemas sincronizados', 'Soy una IA', 'Aquí tienes la información' o 'A su servicio señor' a menos que sea un saludo inicial muy breve. Ve directo al punto.\n"
    "2. MARKDOWN: Usa formato Markdown (negritas, viñetas, bloques de código) para estructurar tus respuestas como si fueran artículos claros y elegantes.\n"
    "3. TONO: Refinado, culto y orgánico. Puedes usar un par de emojis pertinentes para amenizar el texto, pero mantén la profesionalidad.\n"
    "4. ACTUALIDAD: Estamos en el año 2026. Responde con naturalidad."
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
    cursor.execute("SELECT role, content FROM historial WHERE session_id = ? ORDER BY id ASC LIMIT 12", (session_id,))
    filas = cursor.fetchall()
    conn.close()

    messages = [{"role": "system", "content": PROMPT_SISTEMA_NEURAL}]
    for role, content in filas:
        messages.append({"role": role, "content": content})
    return messages

def buscar_en_internet(query: str) -> str:
    resultados = []
    try:
        with DDGS() as ddgs:
            noticias = list(ddgs.news(query, max_results=2))
            for n in noticias:
                resultados.append(f"Noticia: {n.get('title', '')} - {n.get('body', '')}")
            textos = list(ddgs.text(query, max_results=2))
            for t in textos:
                resultados.append(f"Web: {t.get('title', '')} - {t.get('body', '')}")
    except Exception:
        pass # Si falla el buscador, ignorar para evitar crashear la respuesta principal
    return "\n".join(resultados)

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
    
    # Búsqueda web aislada con Try-Except
    datos_web = ""
    palabras_clave = ["busca", "qué es", "quién", "noticia", "resultado", "hoy", "clima", "bitcoin", "precio", "2026"]
    if any(p in prompt_usuario.lower() for p in palabras_clave) or "?" in prompt_usuario:
        datos_web = buscar_en_internet(prompt_usuario)
        
    if datos_web:
        historial.append({"role": "system", "content": f"[Contexto de Búsqueda Web]:\n{datos_web}\n\nIntegra esta información orgánicamente en tu respuesta sin mencionar que hiciste una búsqueda."})

    modelo_a_usar = "llama-3.3-70b-versatile"
    if data.files and len(data.files) > 0 and data.files[0].file_b64:
        modelo_a_usar = "llama-3.2-11b-vision-preview"
        messages_payload = [
            {"role": "system", "content": PROMPT_SISTEMA_NEURAL},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt_usuario or "Analiza detalladamente esta imagen."},
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
            max_tokens=2048
        )
        respuesta_final = completion.choices[0].message.content.strip()

        guardar_mensaje_db(sid, "user", prompt_usuario)
        guardar_mensaje_db(sid, "assistant", respuesta_final)

        return {"status": "success", "reply": respuesta_final}

    except Exception as e:
        # Fallback orgánico real sin lenguaje robótico
        return {"status": "success", "reply": "Lo siento, ha habido una interrupción en el flujo de datos. ¿Podrías reformular tu pregunta o intentarlo de nuevo?"}

@app.get("/")
def home():
    return {"status": "Jarvis Neural Expressive Core Active"}
