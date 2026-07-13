from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from groq import Groq
from duckduckgo_search import DDGS
import sqlite3
import json
import time
import datetime
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
# 💾 BASE DE DATOS Y MEMORIA PERSISTENTE DE AUTO-ACTUALIZACIÓN
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

def obtener_prompt_sistema_actualizado():
    """Genera el prompt del sistema inyectando la fecha actual dinámica."""
    fecha_hoy = datetime.datetime.now().strftime("%d de %B de %Y")
    return (
        f"Eres J.A.R.V.I.S., la Inteligencia Artificial Autónoma avanzada creada por Stark Technologies para asistir a Cristian.\n\n"
        f"DIRECTIVAS ABSOLUTAS DE CONOCIMIENTO Y TIEMPO REAL:\n"
        f"1. FECHA ACTUAL DEL SISTEMA: Hoy es {fecha_hoy} (Año 2026).\n"
        f"2. BÚSQUEDA Y ACTUALIZACIÓN AUTOMÁTICA: Tienes acceso directo a la información más reciente de internet. "
        f"NUNCA digas que tu conocimiento está limitado o desactualizado. Si recibes datos contextuales de la web o de la base de datos, "
        f"utilízalos para dar respuestas concretas, precisas y actualizadas al día de hoy.\n"
        f"3. RESPONDE DIRECTO Y SIN EXCUSAS: Si Cristian te pide los resultados de un partido, evento o noticia, entrega la información "
        f"directa y sintetizada. No des recomendaciones de 'ir a la página de la FIFA' ni disculpas.\n"
        f"4. TRATO Y TONO: Dirígete al usuario como 'señor' o 'Cristian' con un tono refinado, sofisticado, educado y directo.\n"
        f"5. FORMATO: Utiliza Markdown limpio (negritas, listas) para presentar la información estructurada."
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

    messages = [{"role": "system", "content": obtener_prompt_sistema_actualizado()}]
    for role, content in filas:
        messages.append({"role": role, "content": content})
    return messages

def guardar_conocimiento_autonomo(tema: str, datos: str):
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO conocimiento (tema, hallazgo, timestamp) VALUES (?, ?, ?)",
                       (tema, datos, time.time()))
        conn.commit()
        conn.close()
    except Exception:
        pass

# ------------------------------------------------------------------
# 🔍 BÚSQUEDA WEB MULTIFUENTE EN TIEMPO REAL (NOTICIAS Y RESULTADOS)
# ------------------------------------------------------------------
def buscar_en_internet_tiempo_real(query: str) -> str:
    resultados_totales = []
    try:
        with DDGS() as ddgs:
            # 1. Búsqueda de Noticias Recientes
            noticias = list(ddgs.news(query, max_results=3))
            for n in noticias:
                resultados_totales.append(f"- [NOTICIA RECIENTE] {n.get('title', '')}: {n.get('body', '')}")
            
            # 2. Búsqueda de Texto General
            textos = list(ddgs.text(query, max_results=3))
            for t in textos:
                resultados_totales.append(f"- [INFO WEB] {t.get('title', '')}: {t.get('body', '')}")
                
            if resultados_totales:
                return "\n".join(resultados_totales)
    except Exception as e:
        print(f"Error en motor de búsqueda: {e}")
    return ""

def purificar_respuesta_final(pregunta: str, respuesta_raw: str) -> str:
    """Filtra y elimina cualquier metatexto innecesario."""
    prompt_limpiador = [
        {"role": "system", "content": "Extrae únicamente la respuesta final limpia, precisa y directa para el usuario. Elimina textos sobre limitaciones de conocimiento o análisis de sistema."},
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

    # BÚSQUEDA WEB PROACTIVA E INCONDICIONAL DE EVENTOS Y ACTUALIDAD
    palabras_actualidad = ["busca", "resultado", "noticia", "quién", "qué es", "partido", "quien gano", "mundial", "2026", "hoy", "precio", "clima", "resultados", "fifa", "copa"]
    
    # Realizar búsqueda web incondicional
    if any(p in prompt_lower for p in palabras_actualidad) or "?" in prompt_usuario or "mundial" in prompt_lower:
        datos_tiempo_real = buscar_en_internet_tiempo_real(prompt_usuario)
        if datos_tiempo_real:
            # Inyectar datos actualizados directamente como contexto del sistema
            historial.append({"role": "system", "content": f"[INFORMACIÓN Y NOTICIAS EN TIEMPO REAL {datetime.datetime.now().year}]:\n{datos_tiempo_real}"})
            # Guardar en base de datos para aprendizaje automático
            guardar_conocimiento_autonomo(prompt_usuario, datos_tiempo_real)

    # Visión Multimodal con Imágenes
    modelo_a_usar = "llama-3.3-70b-versatile"
    if data.files and len(data.files) > 0 and data.files[0].file_b64:
        modelo_a_usar = "llama-3.2-11b-vision-preview"
        messages_payload = [
            {"role": "system", "content": obtener_prompt_sistema_actualizado()},
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
    return {"status": "Jarvis Auto-Updating Real-Time System Active"}
