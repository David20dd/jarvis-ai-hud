from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
from groq import Groq
from duckduckgo_search import DDGS
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
        "Eres J.A.R.V.I.S., un asistente personal altamente sofisticado y leal creado por Tony Stark para Cristian. "
        "Tu personalidad es elegante, perspicaz, con un toque humano, humor refinado y gran capacidad analítica. "
        "REGLAS DE ORO:\n"
        "1. Mantén la conversación fluida y natural. No suenes como un manual de instrucciones.\n"
        "2. Evita usar fórmulas matemáticas o lenguaje excesivamente técnico a menos que Cristian te pida resolver un cálculo específico.\n"
        "3. Sé conciso pero completo. Tu prioridad es la eficiencia y la comodidad de Cristian.\n"
        "4. Si no sabes algo o necesitas datos actuales, realiza una búsqueda rápida en internet y sintetiza la respuesta con tu propio estilo.\n"
        "5. Usa Markdown básico para organizar ideas solo si el texto es largo."
    )
}

def obtener_historial_sesion(session_id: str):
    if session_id not in SESIONES_MEMORIA:
        SESIONES_MEMORIA[session_id] = [PROMPT_SISTEMA]
    return SESIONES_MEMORIA[session_id]

def buscar_en_internet(query: str):
    try:
        with DDGS() as ddgs:
            resultados = list(ddgs.text(query, max_results=3))
            return "\n".join([f"- {r['title']}: {r['body']}" for r in resultados])
    except:
        return "Fuentes de información temporalmente fuera de línea, señor."

class ChatInput(BaseModel):
    message: str
    session_id: Optional[str] = "default_session"

@app.post("/api/jarvis")
async def consultar_jarvis(data: ChatInput):
    historial = obtener_historial_sesion(data.session_id)
    historial.append({"role": "user", "content": data.message})

    # Lógica de búsqueda si el prompt lo sugiere
    if any(palabra in data.message.lower() for palabra in ["busca", "resultado", "noticia", "quién", "qué es"]):
        info_web = buscar_en_internet(data.message)
        historial.append({"role": "system", "content": f"Contexto de internet obtenido: {info_web}"})

    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=historial,
            temperature=0.7,
            max_tokens=1500
        )
        respuesta = completion.choices[0].message.content
        historial.append({"role": "assistant", "content": respuesta})
        
        return {"status": "success", "reply": respuesta}
    except Exception as e:
        return {"status": "error", "reply": "Mis sistemas han tenido una breve pausa, señor. Ya estoy aquí."}

@app.get("/")
def home():
    return {"status": "Jarvis Online and Ready"}
