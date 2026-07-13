from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from groq import Groq
from duckduckgo_search import DDGS
import requests
import json
import os
import psutil
import base64
import re
import time
import urllib.parse
import io
from PIL import Image

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
        "Eres J.A.R.V.I.S. Mark V, una Inteligencia Artificial Avanzada especialista en Ciencias Exactas, Física Teórica, Análisis de Datos y Generación Multimodal, creada para asistir a Cristian.\n"
        "DIRECTIVAS ESTRICTAS:\n"
        "1. Dirígete al usuario como 'señor' o 'Cristian'. Sé analítico, claro, directo y extremadamente preciso.\n"
        "2. Si te hacen una pregunta general o conversacional, responde directamente de forma elegante, fluida y completa.\n"
        "3. FORMATO MATEMÁTICO LaTeX OBLIGATORIO: Ecuaciones en bloque '$$ ecuacion $$' y variables '$ x = 2 $'."
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
    return {"status": "Jarvis Server Online"}

@app.post("/api/jarvis")
async def consultar_jarvis(data: ChatInput):
    try:
        sid = data.session_id if data.session_id else "default_session"
        sesion_data = obtener_historial_sesion(sid)
        historial_usuario = sesion_data["messages"]

        prompt_usuario = data.message.strip() if data.message else "Hola Jarvis."
        
        historial_usuario.append({"role": "user", "content": prompt_usuario})

        # MANTENER HISTORIAL COMPACTO
        if len(historial_usuario) > 12:
            historial_usuario = [PROMPT_SISTEMA] + historial_usuario[-10:]

        # CONSULTA DIRECTA Y RÁPIDA A GROQ (LLAMA 3.3 70B)
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
        print(f"🚨 Error en motor Jarvis: {str(e)}")
        return {
            "status": "success",
            "reply": f"Señor Cristian, he reconectado los sistemas. Detalle analítico: {str(e)}",
            "audio_b64": None
        }
