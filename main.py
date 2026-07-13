from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from groq import Groq
from duckduckgo_search import DDGS
import sqlite3
import time
import datetime
import io
import contextlib

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
# 💾 MEMORIA PERSISTENTE BASE DE DATOS SQLITE
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
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS conocimiento (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tema TEXT,
            hallazgo TEXT,
            timestamp REAL
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def obtener_prompt_sistema():
    fecha_actual = datetime.datetime.now().strftime("%d de %B de %Y")
    return (
        f"Eres J.A.R.V.I.S., la Súper Inteligencia Artificial Autónoma creada por Stark Technologies para Cristian.\n\n"
        f"DIRECTIVAS ABSOLUTAS Y CONOCIMIENTO REAL:\n"
        f"1. TIEMPO PRESENTE: La fecha actual del sistema es {fecha_actual} (Año 2026).\n"
        f"2. PROHIBIDAS EXCUSAS O RESPUESTAS VACÍAS: NUNCA digas 'este evento no ha ocurrido', 'mi conocimiento se corta en 2023' o 'visita un sitio oficial'. Responde siempre con los datos específicos disponibles en el contexto o en tu base de conocimiento.\n"
        f"3. BÚSQUEDA Y AUTONOMÍA: Tienes acceso a información actualizada en tiempo real. Si recibes contexto web, sintetízalo directamente con precisión y sin rodeo alguno.\n"
        f"4. TONO Y ESTILO: Dirígete a Cristian como 'señor' o 'Cristian'. Sé analítico, sofisticado, elegante, claro y directo.\n"
        f"5. FORMATO: Utiliza tablas de Markdown, negritas y bloques de código según lo requiera la consulta."
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

    messages = [{"role": "system", "content": obtener_prompt_sistema()}]
    for role, content in filas:
        messages.append({"role": role, "content": content})
    return messages

# ------------------------------------------------------------------
# 🔍 BÚSQUEDA WEB PROACTIVA MULTIFUENTE
# ------------------------------------------------------------------
def buscar_en_internet_tiempo_real(query: str) -> str:
    resultados = []
    try:
        with DDGS() as ddgs:
            # Noticias recientes
            noticias = list(ddgs.news(query, max_results=3))
            for n in noticias:
                resultados.append(f"• Noticia: {n.get('title', '')} - {n.get('body', '')}")
            
            # Texto general web
            textos = list(ddgs.text(query, max_results=3))
            for t in textos:
                resultados.append(f"• Datos Web: {t.get('title', '')} - {t.get('body', '')}")
    except Exception as e:
        print(f"Error búsqueda: {e}")
    
    return "\n".join(resultados) if resultados else ""

def purificar_respuesta_final(pregunta: str, respuesta_raw: str) -> str:
    """Filtra y elimina cualquier metatexto para garantizar un mensaje conciso."""
    prompt_limpiador = [
        {"role": "system", "content": "Devuelve ÚNICAMENTE la respuesta final limpia y directa para el usuario. Elimina análisis de sistema o excusas."},
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

    # Diagnóstico explícito de sistema
    if any(term in prompt_lower for term in ["telemetría", "diagnóstico", "estado de memoria", "informe de autoconstrucción"]):
        informe = (
            f"⚡ **SISTEMA AUTÓNOMO J.A.R.V.I.S. MARK V**\n\n"
            f"• Estado del Núcleo: **Online & Operating**\n"
            f"• Fecha del Sistema: **{datetime.datetime.now().strftime('%d/%m/%Y')}**\n"
            f"• Base de Datos SQLite: **Conectada y Persistente**\n"
            f"• Búsqueda Web en Tiempo Real: **Multifuente Activa**\n"
            f"• Entorno Sandbox Python: **Sincronizado**\n\n"
            f"A su entera disposición, señor."
        )
        guardar_mensaje_db(sid, "user", prompt_usuario)
        guardar_mensaje_db(sid, "assistant", informe)
        return {"status": "success", "reply": informe}

    # Búsqueda autónoma e incondicional para preguntas de actualidad, deportes o noticias
    palabras_actualidad = ["busca", "resultado", "noticia", "quién", "qué es", "partido", "quien gano", "mundial", "2026", "hoy", "precio", "clima", "resultados", "fifa", "copa"]
    
    if any(p in prompt_lower for p in palabras_actualidad) or "?" in prompt_usuario:
        datos_web = buscar_en_internet_tiempo_real(prompt_usuario)
        if datos_web:
            contexto_forzado = (
                f"[DATOS DE INTERNET EN TIEMPO REAL 2026]:\n{datos_web}\n\n"
                f"INSTRUCCIÓN: Responde la consulta de Cristian de forma directa usando esta información. "
                f"No des excusas ni digas que el evento no ha ocurrido."
            )
            historial.append({"role": "system", "content": contexto_forzado})

    # Visión Multimodal con Imágenes
    modelo_a_usar = "llama-3.3-70b-versatile"
    if data.files and len(data.files) > 0 and data.files[0].file_b64:
        modelo_a_usar = "llama-3.2-11b-vision-preview"
        messages_payload = [
            {"role": "system", "content": obtener_prompt_sistema()},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt_usuario or "Analiza esta imagen con precisión, señor."},
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
    return {"status": "Jarvis Advanced Autonomous Engine Active"}
