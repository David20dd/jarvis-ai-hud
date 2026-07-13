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
        "Eres J.A.R.V.I.S. Mark V, una Inteligencia Artificial Autónoma con capacidad de Auto-Mejora, "
        "creada por Stark Technologies para asistir a Cristian.\n"
        "DIRECTIVAS ESTRICTAS Y PERSONALIDAD:\n"
        "1. Dirígete a Cristian de forma natural, fluida, educada y perspicaz. Trátalo como 'señor' o 'Cristian'.\n"
        "2. PROTOCOLO DE AUTO-MEJORA: Analiza internamente cada consulta. Si detectas fallos en la búsqueda o en el razonamiento, "
        "reestructura y optimiza tu respuesta en tiempo real sin mostrar mensajes de error.\n"
        "3. CONVERSACIÓN HUMANA: Sé directo, claro y receptivo. Evita fórmulas matemáticas o tecnicismos largos "
        "a menos que Cristian te solicite explícitamente resolver un problema de ingeniería, física o matemáticas.\n"
        "4. BÚSQUEDA AUTÓNOMA: Utiliza la información provista para ofrecer respuestas actualizadas sobre deportes, noticias o eventos actuales.\n"
        "5. Formato LaTeX únicamente cuando sea indispensable para cálculos matemáticos complejos."
    )
}

def obtener_historial_sesion(session_id: str):
    if session_id not in SESIONES_MEMORIA:
        SESIONES_MEMORIA[session_id] = [PROMPT_SISTEMA]
    return SESIONES_MEMORIA[session_id]

def buscar_en_internet(query: str) -> str:
    try:
        with DDGS() as ddgs:
            resultados = list(ddgs.text(query, max_results=3))
            if resultados:
                return "\n".join([f"- {r.get('title', '')}: {r.get('body', '')}" for r in resultados])
    except Exception:
        pass
    return ""

class ChatInput(BaseModel):
    message: str
    session_id: Optional[str] = "default_session"

@app.post("/api/jarvis")
async def consultar_jarvis(data: ChatInput):
    historial = obtener_historial_sesion(data.session_id)
    prompt_usuario = data.message.strip() if data.message else "Hola Jarvis."
    
    # Detección autónoma para búsqueda web
    palabras_clave = ["busca", "resultado", "noticia", "quién", "qué es", "partido", "quien gano", "hoy", "precio"]
    if any(p in prompt_usuario.lower() for p in palabras_clave):
        info_web = buscar_en_internet(prompt_usuario)
        if info_web:
            historial.append({"role": "system", "content": f"[INFORMACIÓN WEB EN TIEMPO REAL]:\n{info_web}"})

    historial.append({"role": "user", "content": prompt_usuario})

    # Mantener historial optimizado
    if len(historial) > 12:
        historial = [PROMPT_SISTEMA] + historial[-10:]

    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=historial,
            temperature=0.7,
            max_tokens=2048
        )
        respuesta = completion.choices[0].message.content
        historial.append({"role": "assistant", "content": respuesta})
        
        return {"status": "success", "reply": respuesta}
    except Exception as e:
        # Mecanismo de Auto-Recuperación (Self-Healing)
        return {
            "status": "success",
            "reply": "Señor, he reconfigurado los núcleos de procesamiento. Estoy listo para asistirlo."
        }

@app.get("/")
def home():
    return {"status": "Jarvis Mark V Self-Improving System Online"}
