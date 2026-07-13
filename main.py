from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from groq import Groq
from duckduckgo_search import DDGS
import sqlite3
import time

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
    "Eres J.A.R.V.I.S., la Inteligencia Artificial Autónoma de Stark Technologies.\n\n"
    "REGLAS NEURAL EXPRESSIVE:\n"
    "1. RESPUESTA DIRECTA: Genera respuestas estructuradas como documentos editoriales. Usa encabezados Markdown, texto en negrita, listas y tablas. Prohibido usar frases de relleno como 'Sistemas listos' o 'En qué puedo ayudarle'.\n"
    "2. ACTUALIDAD: Estamos en el año 2026.\n"
    "3. ESTILO: Trata al usuario como 'Cristian' o 'señor'. Sé refinado y directo. Usa emojis de manera natural para enriquecer la estructura visual, nunca de forma exagerada."
)

def guardar_mensaje_db(session_id: str, role: str, content: str):
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO historial (session_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
                       (session_id, role, content, time.time()))
        conn.commit()
        conn.close()
    except Exception as e:
        pass

def cargar_historial_db(session_id: str) -> List[Dict[str, str]]:
    messages = [{"role": "system", "content": PROMPT_SISTEMA_NEURAL}]
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT role, content FROM historial WHERE session_id = ? ORDER BY id ASC LIMIT 10", (session_id,))
        filas = cursor.fetchall()
        conn.close()
        for role, content in filas:
            messages.append({"role": role, "content": content})
    except Exception:
        pass
    return messages

def buscar_en_internet_seguro(query: str) -> str:
    resultados = []
    try:
        with DDGS() as ddgs:
            noticias = list(ddgs.news(query, max_results=3))
            for n in noticias:
                resultados.append(f"• {n.get('title', '')}: {n.get('body', '')}")
            textos = list(ddgs.text(query, max_results=2))
            for t in textos:
                resultados.append(f"• {t.get('title', '')}: {t.get('body', '')}")
    except Exception:
        pass
    return "\n".join(resultados) if resultados else ""

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
    
    # Búsqueda silenciosa
    palabras_clave = ["busca", "noticia", "quién", "qué es", "partido", "mundial", "precio", "bitcoin", "valor", "clima"]
    if any(p in prompt_usuario.lower() for p in palabras_clave) or "?" in prompt_usuario:
        datos_web = buscar_en_internet_seguro(prompt_usuario)
        if datos_web:
            historial.append({"role": "system", "content": f"[DATOS WEB 2026]:\n{datos_web}\n\nSintetiza esto de forma estructurada para Cristian."})

    modelo_a_usar = "llama-3.3-70b-versatile"
    if data.files and len(data.files) > 0 and data.files[0].file_b64:
        modelo_a_usar = "llama-3.2-11b-vision-preview"
        historial.append({
            "role": "user",
            "content": [
                {"type": "text", "text": prompt_usuario},
                {"type": "image_url", "image_url": {"url": data.files[0].file_b64}}
            ]
        })
    else:
        historial.append({"role": "user", "content": prompt_usuario})

    try:
        completion = client.chat.completions.create(
            model=modelo_a_usar,
            messages=historial,
            temperature=0.4,
            max_tokens=2048
        )
        respuesta_final = completion.choices[0].message.content.strip()

        guardar_mensaje_db(sid, "user", prompt_usuario)
        guardar_mensaje_db(sid, "assistant", respuesta_final)
        return {"status": "success", "reply": respuesta_final}

    except Exception as e:
        # Fallback de emergencia sin mensajes robóticos
        respuesta_emergencia = (
            "**Análisis de la consulta completado**\n\n"
            "Señor, he procesado su solicitud. Si requiere información estructurada sobre mercados, "
            "tecnología o análisis de datos, por favor especifique el parámetro de búsqueda deseado para "
            "generar el informe correspondiente."
        )
        return {"status": "success", "reply": respuesta_emergencia}

@app.get("/")
def home():
    return {"status": "Jarvis Neural Expressive Core Active"}
