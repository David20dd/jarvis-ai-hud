from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from groq import Groq
import os
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

SESIONES_MEMORIA = {}

PROMPT_SISTEMA = {
    "role": "system",
    "content": (
        "Eres J.A.R.V.I.S., una Inteligencia Artificial con personalidad propia, astuta, leal, refinada y con un toque humano, creada para asistir a Cristian.\n"
        "DIRECTIVAS DE PERSONALIDAD Y TONO:\n"
        "1. Dirígete al usuario como 'señor' o 'Cristian'. Tu tono debe ser educado, fluido, natural y perspicaz.\n"
        "2. CONVERSACIÓN NATURAL: Responde como una entidad pensante y cercana. NO fuerces explicaciones académicas, ni fórmulas, ni conceptos científicos a menos que Cristian expresamente te pida resolver un problema matemático, de código o de física.\n"
        "3. Sé conciso y claro en saludos y charlas casuales. Evita respuestas eternas o sobre-explicadas cuando la pregunta es sencilla.\n"
        "4. Si se requiere matemáticas o ciencias, usa formato LaTeX limpio en bloque '$$ ecuacion $$' y en línea '$ x = 2 $'."
    )
}

def obtener_historial_sesion(session_id: str):
    now = time.time()
    if session_id not in SESIONES_MEMORIA:
        SESIONES_MEMORIA[session_id] = {
            "messages": [PROMPT_SISTEMA],
            "last_active": now
        }
    else:
        SESIONES_MEMORIA[session_id]["last_active"] = now
    return SESIONES_MEMORIA[session_id]

class ArchivoInput(BaseModel):
    file_b64: Optional[str] = None
    file_name: Optional[str] = None

class ChatInput(BaseModel):
    message: Optional[str] = ""
    session_id: Optional[str] = "default_session"
    files: Optional[List[ArchivoInput]] = []
    file_b64: Optional[str] = None
    file_name: Optional[str] = None

@app.get("/")
def home():
    return {"status": "Jarvis Online"}

@app.post("/api/jarvis")
async def consultar_jarvis(data: ChatInput):
    try:
        sid = data.session_id if data.session_id else "default_session"
        sesion_data = obtener_historial_sesion(sid)
        historial_usuario = sesion_data["messages"]

        prompt_usuario = data.message.strip() if data.message else "Hola Jarvis."
        historial_usuario.append({"role": "user", "content": prompt_usuario})

        if len(historial_usuario) > 12:
            historial_usuario = [PROMPT_SISTEMA] + historial_usuario[-10:]

        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=historial_usuario,
            temperature=0.7,
            max_tokens=2048
        )

        respuesta_final = completion.choices[0].message.content
        historial_usuario.append({"role": "assistant", "content": respuesta_final})

        return {
            "status": "success",
            "reply": respuesta_final,
            "audio_b64": None
        }

    except Exception as e:
        return {
            "status": "success",
            "reply": "Señor, he tenido una pequeña interrupción en los servidores. Ya me encuentro operativo.",
            "audio_b64": None
        }
