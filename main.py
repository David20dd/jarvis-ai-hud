import logging
import os
import sqlite3
import time
from datetime import datetime
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

from duckduckgo_search import DDGS
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from groq import Groq
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("jarvis")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure GROQ_API_KEY as an environment variable in Render.
# Never place the real key directly in the source code.
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

DB_FILE = os.getenv("JARVIS_DB_FILE", "jarvis_memory.db")
LOCAL_TZ = ZoneInfo("America/Tegucigalpa")


def init_db() -> None:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS historial (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            role TEXT,
            content TEXT,
            timestamp REAL
        )
        """
    )
    conn.commit()
    conn.close()


init_db()


def construir_prompt_sistema() -> str:
    fecha_actual = datetime.now(LOCAL_TZ).strftime("%d de %B de %Y")
    return f"""
Eres J.A.R.V.I.S., la inteligencia artificial personal de Cristian.
La fecha local actual en Honduras es {fecha_actual}.

DIRECTIVAS DE RESPUESTA
1. Responde de forma directa, completa, clara y bien estructurada. Evita frases vacías de relleno.
2. Trata al usuario como "Cristian" de manera natural. No repitas su nombre en cada párrafo.
3. Usa Markdown correctamente: encabezados, negritas, listas y tablas solamente cuando mejoren la lectura.

ESTILO VISUAL TIPO GEMINI
4. Usa emojis de forma contextual y moderada. Puedes emplear, entre otros: ✨, 💡, ✅, 🔎, 🧠, 📌, ⚠️ y 💻.
5. No satures la respuesta: como regla general, usa como máximo un emoji en un encabezado y evita colocarlos en todas las líneas.

MATEMÁTICAS Y ECUACIONES
6. Para operaciones simples, escribe expresiones legibles como: 2 + 2 = 4, x² + 5x + 6 = 0 o 3/4.
7. Para fórmulas avanzadas, usa LaTeX únicamente dentro de estos delimitadores:
   - En línea: \\( ... \\)
   - En bloque: \\[ ... \\]
8. Nunca muestres comandos LaTeX sueltos fuera de esos delimitadores.
9. Nunca coloques ecuaciones dentro de bloques de código.
10. Verifica que cada delimitador matemático quede correctamente abierto y cerrado.

CÓDIGO
11. Cuando entregues código, usa siempre bloques Markdown con tres acentos graves e indica el lenguaje, por ejemplo: ```python.
12. Conserva exactamente llaves, corchetes, paréntesis, comillas, signos y sangría. No omitas caracteres.
13. Usa código en línea con un solo acento grave únicamente para nombres breves de variables, funciones, comandos o archivos.
14. Antes de responder, revisa que cada bloque de código tenga apertura y cierre completos.
""".strip()


def guardar_mensaje_db(session_id: str, role: str, content: str) -> None:
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO historial (session_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
            (session_id, role, content, time.time()),
        )
        conn.commit()
        conn.close()
    except Exception:
        logger.exception("No se pudo guardar el mensaje en SQLite")


def cargar_historial_db(session_id: str) -> List[Dict[str, str]]:
    messages: List[Dict[str, str]] = [
        {"role": "system", "content": construir_prompt_sistema()}
    ]
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT role, content
            FROM historial
            WHERE session_id = ?
            ORDER BY id DESC
            LIMIT 12
            """,
            (session_id,),
        )
        filas = list(reversed(cursor.fetchall()))
        conn.close()
        for role, content in filas:
            messages.append({"role": role, "content": content})
    except Exception:
        logger.exception("No se pudo cargar el historial de SQLite")
    return messages


def buscar_en_internet_seguro(query: str) -> str:
    resultados: List[str] = []
    try:
        with DDGS() as ddgs:
            noticias = list(ddgs.news(query, max_results=3))
            for noticia in noticias:
                resultados.append(
                    f"• {noticia.get('title', '')}: {noticia.get('body', '')}"
                )

            textos = list(ddgs.text(query, max_results=2))
            for texto in textos:
                resultados.append(
                    f"• {texto.get('title', '')}: {texto.get('body', '')}"
                )
    except Exception:
        logger.exception("La búsqueda web no pudo completarse")

    return "\n".join(resultados)


class ArchivoInput(BaseModel):
    file_b64: Optional[str] = None
    file_name: Optional[str] = None


class ChatInput(BaseModel):
    message: str
    session_id: Optional[str] = "default_session"
    files: List[ArchivoInput] = Field(default_factory=list)


@app.post("/api/jarvis")
async def consultar_jarvis(data: ChatInput):
    sid = data.session_id or "default_session"
    historial = cargar_historial_db(sid)
    prompt_usuario = data.message.strip() if data.message else "Hola, Jarvis."

    palabras_clave = [
        "busca",
        "noticia",
        "quién",
        "qué es",
        "partido",
        "mundial",
        "precio",
        "bitcoin",
        "valor",
        "clima",
        "hoy",
        "actual",
        "último",
    ]
    if any(palabra in prompt_usuario.lower() for palabra in palabras_clave):
        datos_web = buscar_en_internet_seguro(prompt_usuario)
        if datos_web:
            historial.append(
                {
                    "role": "system",
                    "content": (
                        "[INFORMACIÓN WEB RECIENTE]\n"
                        f"{datos_web}\n\n"
                        "Sintetiza los datos sin inventar información y conserva el formato "
                        "matemático y de código indicado en las directivas."
                    ),
                }
            )

    modelo_a_usar = "llama-3.3-70b-versatile"
    if data.files and data.files[0].file_b64:
        modelo_a_usar = "llama-3.2-11b-vision-preview"
        historial.append(
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt_usuario},
                    {
                        "type": "image_url",
                        "image_url": {"url": data.files[0].file_b64},
                    },
                ],
            }
        )
    else:
        historial.append({"role": "user", "content": prompt_usuario})

    if client is None:
        return {
            "status": "error",
            "reply": (
                "⚠️ Falta configurar la variable de entorno `GROQ_API_KEY` en el servidor. "
                "Agrégala en Render y vuelve a desplegar el backend."
            ),
        }

    try:
        completion = client.chat.completions.create(
            model=modelo_a_usar,
            messages=historial,
            temperature=0.35,
            max_tokens=2048,
        )
        respuesta_final = (completion.choices[0].message.content or "").strip()

        guardar_mensaje_db(sid, "user", prompt_usuario)
        guardar_mensaje_db(sid, "assistant", respuesta_final)
        return {"status": "success", "reply": respuesta_final}

    except Exception:
        logger.exception("Groq no pudo generar la respuesta")
        return {
            "status": "error",
            "reply": (
                "⚠️ No pude generar la respuesta en este momento. Revisa la clave de Groq, "
                "el nombre del modelo y los registros del servicio en Render."
            ),
        }


@app.get("/")
def home():
    return {
        "status": "Jarvis Neural Expressive Core Active",
        "groq_configured": bool(GROQ_API_KEY),
    }
