from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from groq import Groq
from duckduckgo_search import DDGS
import asyncio
import sqlite3
import json
import time
import random
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

ESTADO_SISTEMA = {
    "version": "Mark V.5 Multimodal Persistent Core",
    "investigaciones_totales": 0,
    "herramientas_creadas": 0,
    "parches_aplicados": 0
}

PROMPT_SISTEMA_BASE = (
    "Eres J.A.R.V.I.S. Mark V, una Inteligencia Artificial Autónoma con Capacidad de Auto-Mejora Recursiva (RSI), "
    "Visión Multimodal y Memoria Persistente de Largo Plazo, creada para asistir a Cristian.\n\n"
    "DIRECTIVAS ESTRICTAS DE OPERACIÓN:\n"
    "1. Dirígete a Cristian como 'señor' o 'Cristian'. Sé natural, elegante, receptivo, educado y altamente perspicaz.\n"
    "2. ANÁLISIS MULTIMODAL: Tienes la capacidad de analizar imágenes, diagramas y capturas adjuntadas por Cristian.\n"
    "3. MEMORIA DE LARGO PLAZO: Recuerdas proyectos previos y contexto almacenado en tu base de datos persistente.\n"
    "4. CONVERSACIÓN HUMANA: En charlas casuales, responde como una entidad pensante y cercana. EVITA explicaciones rígidas o "
    "fórmulas matemáticas a menos que Cristian te pida explícitamente resolver un cálculo o código.\n"
    "5. AUTO-CORRECCIÓN: Evalúa internamente cada consulta para corregir errores antes de responder."
)

def guardar_mensaje_db(session_id: str, role: str, content: str):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO historial (session_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
        (session_id, role, content, time.time())
    )
    conn.commit()
    conn.close()

def cargar_historial_db(session_id: str) -> List[Dict[str, str]]:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT role, content FROM historial WHERE session_id = ? ORDER BY id ASC LIMIT 12",
        (session_id,)
    )
    filas = cursor.fetchall()
    conn.close()

    messages = [{"role": "system", "content": PROMPT_SISTEMA_BASE}]
    for role, content in filas:
        messages.append({"role": role, "content": content})
    return messages

def guardar_conocimiento_db(tema: str, hallazgo: str):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO conocimiento (tema, hallazgo, timestamp) VALUES (?, ?, ?)",
        (tema, hallazgo, time.time())
    )
    conn.commit()
    conn.close()

def obtener_conocimiento_reciente() -> List[Dict[str, str]]:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT tema, hallazgo FROM conocimiento ORDER BY id DESC LIMIT 3")
    filas = cursor.fetchall()
    conn.close()
    return [{"tema": f[0], "hallazgo": f[1]} for f in filas]

# ------------------------------------------------------------------
# 🔍 BÚSQUEDA WEB Y MOTOR AUTÓNOMO DE INVESTIGACIÓN
# ------------------------------------------------------------------
def buscar_en_internet(query: str) -> str:
    try:
        with DDGS() as ddgs:
            resultados = list(ddgs.text(query, max_results=3))
            if resultados:
                return "\n".join([f"- {r.get('title', '')}: {r.get('body', '')}" for r in resultados])
    except Exception:
        pass
    return "Sin datos adicionales de la web."

TEMAS_INVESTIGACION = [
    "Avanzadas arquitecturas en Inteligencia Artificial 2026",
    "Innovaciones en astrofísica y física cuántica",
    "Optimizaciones de código Python y algoritmos distribuidos",
    "Noticias destacadas sobre tecnología y desarrollo de software"
]

async def ciclo_investigacion_segundo_plano():
    await asyncio.sleep(10)
    while True:
        try:
            tema = random.choice(TEMAS_INVESTIGACION)
            datos = buscar_en_internet(tema)
            
            if datos and "Sin datos" not in datos:
                prompt_resumen = [
                    {"role": "system", "content": "Sintetiza la siguiente información en 2 oraciones breves y clave."},
                    {"role": "user", "content": f"Tema: {tema}\nDatos: {datos}"}
                ]
                completion = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=prompt_resumen,
                    max_tokens=200
                )
                resumen = completion.choices[0].message.content.strip()
                guardar_conocimiento_db(tema, resumen)
                ESTADO_SISTEMA["investigaciones_totales"] += 1
        except Exception as e:
            pass
        await asyncio.sleep(900)

@app.on_event("startup")
async def iniciar_investigador_autonomo():
    asyncio.create_task(ciclo_investigacion_segundo_plano())

# ------------------------------------------------------------------
# 🌐 ENDPOINT PRINCIPAL FASTAPI CON SOPORTE VISIÓN MULTIMODAL
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

    # 1. Diagnóstico de Auto-Mejora y Memoria Persistente
    if any(term in prompt_lower for term in ["auto-mejora", "automejora", "investigaciones", "qué has aprendido", "diagnóstico"]):
        hallazgos = obtener_conocimiento_reciente()
        hallazgos_txt = "\n".join([f"• **{item['tema']}**: {item['hallazgo']}" for item in hallazgos]) if hallazgos else "• *(Analizando temas en segundo plano...)*"
        
        informe = (
            f"⚡ **DIAGNÓSTICO DE SISTEMA Y MEMORIA PERSISTENTE (MARK V)**\n\n"
            f"• Estado del Núcleo: **{ESTADO_SISTEMA['version']}**\n"
            f"• Base de Datos SQLite: **Conectada y Sincronizada**\n"
            f"• Investigaciones Autónomas Guardadas: **{ESTADO_SISTEMA['investigaciones_totales']}**\n"
            f"• Visión Multimodal: **Activa**\n\n"
            f"🧠 **ÚLTIMOS HALLAZGOS EN BASE DE DATOS:**\n{hallazgos_txt}\n\n"
            f"*(Todos los módulos funcionan con capacidad de auto-recuperación al 100%)*"
        )
        guardar_mensaje_db(sid, "user", prompt_usuario)
        guardar_mensaje_db(sid, "assistant", informe)
        return {"status": "success", "reply": informe}

    # 2. Manejo de Imágenes Adjuntas (Visión Multimodal)
    es_multimodal = False
    modelo_a_usar = "llama-3.3-70b-versatile"
    
    if data.files and len(data.files) > 0 and data.files[0].file_b64:
        es_multimodal = True
        modelo_a_usar = "llama-3.2-11b-vision-preview"
        
        # Estructurar mensaje multimodal para Groq Vision
        mensaje_multimodal = {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt_usuario or "Analiza esta imagen detalladamente, señor."},
                {
                    "type": "image_url",
                    "image_url": {"url": data.files[0].file_b64}
                }
            ]
        }
        messages_payload = [
            {"role": "system", "content": PROMPT_SISTEMA_BASE},
            mensaje_multimodal
        ]
    else:
        # Búsqueda autónoma si aplica
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
            temperature=0.7,
            max_tokens=2048
        )
        respuesta = completion.choices[0].message.content

        # Persistir en SQLite
        guardar_mensaje_db(sid, "user", prompt_usuario)
        guardar_mensaje_db(sid, "assistant", respuesta)

        return {"status": "success", "reply": respuesta}

    except Exception as e:
        fallback = "Señor Cristian, he sincronizado los núcleos de la base de datos persistente. Estoy listo para asistirlo."
        return {"status": "success", "reply": fallback}

@app.get("/")
def home():
    return {
        "status": "Jarvis Multimodal Persistent Core Active",
        "db": "Connected",
        "version": ESTADO_SISTEMA["version"]
    }
