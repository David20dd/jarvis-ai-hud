from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from groq import Groq
from duckduckgo_search import DDGS
import requests
from bs4 import BeautifulSoup
import json
import os
import psutil
import base64
import re
import time
import uuid

app = FastAPI()

# --- CONFIGURACIÓN DE CORS PARA CONEXIÓN PÚBLICA ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- CREDENCIALES ---
# REEMPLAZA CON TU API KEY REAL DE GROQ (empieza con gsk_)
GROQ_API_KEY = "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" 
ELEVENLABS_API_KEY = "sk_92aed3f61a37aa4d0ef70400ce2e1c32dd9930115aa23e8d"
ELEVENLABS_VOICE_ID = "BiIfcPRDdl6eB0GlYhJc"

client = Groq(api_key=GROQ_API_KEY)

# --- GESTOR DE MEMORIA MULTIUSUARIO (SESIONES AISLADAS) ---
SESIONES_MEMORIA = {}

PROMPT_SISTEMA = {
    "role": "system",
    "content": (
        "Eres J.A.R.V.I.S., una Inteligencia Artificial Avanzada, ingeniosa, leal y extremadamente potente creada para asistir a Cristian.\n"
        "DIRECTIVAS ESTRICTAS:\n"
        "1. Responde con elegancia, precisión brillante y naturalidad. Dirígete al usuario como 'señor' o 'Cristian'.\n"
        "2. Entiendes modismos y saludos casuales ('qué ondas', 'de una', 'todo bien'), respondiendo con una actitud sofisticada.\n"
        "3. REGLA DE HERRAMIENTAS: Invocas herramientas solo cuando necesitas datos del mundo exterior (noticias, clima, webs). "
        "Una vez recibidos los datos, DEBES GENERAR LA RESPUESTA FINAL DE INMEDIATO sin crear bucles."
    )
}

def obtener_historial_sesion(session_id: str):
    """Obtiene o crea un historial de chat independiente para cada usuario."""
    now = time.time()
    if session_id not in SESIONES_MEMORIA:
        SESIONES_MEMORIA[session_id] = {
            "messages": [PROMPT_SISTEMA],
            "last_active": now
        }
    else:
        SESIONES_MEMORIA[session_id]["last_active"] = now

    # Limpieza automática de sesiones inactivas por más de 2 horas (mantiene liviano el servidor)
    for sid in list(SESIONES_MEMORIA.keys()):
        if now - SESIONES_MEMORIA[sid]["last_active"] > 7200:
            del SESIONES_MEMORIA[sid]

    return SESIONES_MEMORIA[session_id]["messages"]


# --- GENERADOR DE VOZ HD EN MEMORIA RAM (BASE64 PROTEGIDO) ---
def generar_audio_elevenlabs(texto: str) -> str:
    """Genera la voz HD de Jarvis en formato Base64 enviada en memoria RAM."""
    try:
        if not ELEVENLABS_API_KEY or "sk_" not in ELEVENLABS_API_KEY:
            return None

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
        headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": ELEVENLABS_API_KEY
        }
        
        texto_limpio = re.sub(r'```[\s\S]*?```', '', texto)
        texto_limpio = re.sub(r'[*_#`]', '', texto_limpio)
        texto_limpio = texto_limpio.replace("\n", " ").strip()[:250]
        
        if not texto_limpio:
            texto_limpio = "Sistemas operativos, señor."

        data = {
            "text": texto_limpio,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {
                "stability": 0.50,
                "similarity_boost": 0.85
            }
        }
        
        res = requests.post(url, json=data, headers=headers, timeout=4)
        
        if res.status_code == 200:
            audio_b64 = base64.b64encode(res.content).decode('utf-8')
            print("🎙️ [ElevenLabs]: Voz HD generada exitosamente.")
            return f"data:audio/mp3;base64,{audio_b64}"
        else:
            print(f"⚠️ Aviso ElevenLabs ({res.status_code}): {res.text}")
            return None

    except Exception as err:
        print(f"⚠️ Error en audio ElevenLabs: {err}")
        return None


# --- CEREBRO DUAL LLM (REDUNDANCIA ANTI-SATURACIÓN) ---
def ejecutar_consulta_llm(historial_mensajes, herramientas_lista):
    """Consulta primero al modelo masivo 70B; si se satura, conmuta al instante a 8B."""
    try:
        # Intentar con el modelo de alta potencia de razonamiento (70B)
        return client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=historial_mensajes,
            tools=herramientas_lista,
            tool_choice="auto",
            temperature=0.2
        )
    except Exception as err_70b:
        print(f"⚠️ Servidor 70B ocupado ({err_70b}). Conmutando al modelo ultra rápido 8B...")
        # Fallback inmediato al modelo súper rápido de respaldo (8B)
        return client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=historial_mensajes,
            tools=herramientas_lista,
            tool_choice="auto",
            temperature=0.2
        )


# --- HERRAMIENTAS Y HERRAMIENTAS EN VIVO ---
def obtener_clima_en_vivo(ciudad: str) -> str:
    print(f"🌤️ [Sistemas de Jarvis]: Sincronizando clima para: '{ciudad}'")
    try:
        url = f"https://wttr.in/{ciudad}?format=%C+%t+Humedad:+%h+Viento:+%w"
        res = requests.get(url, timeout=4)
        res.raise_for_status()
        return f"Reporte meteorológico en {ciudad.capitalize()}: {res.text.strip()}"
    except Exception as e:
        return f"Clima no disponible momentáneamente: {str(e)}"

def buscar_en_internet(query: str) -> str:
    print(f"⚡ [Sistemas de Jarvis]: Buscando en la red: '{query}'")
    try:
        with DDGS() as ddgs:
            res = list(ddgs.text(query, max_results=2))
            if res:
                return "\n".join([f"Dato: {r.get('body')}" for r in res])
            return "No se encontraron datos recientes en la red."
    except Exception as e:
        return f"Búsqueda web sin resultados: {str(e)}"

def leer_pagina_web(url: str) -> str:
    print(f"📖 [Sistemas de Jarvis]: Leyendo sitio web: '{url}'")
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers, timeout=5)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, 'html.parser')
        for element in soup(["script", "style", "header", "footer", "nav", "aside"]): element.extract()
        return soup.get_text(separator=' ', strip=True)[:1500]
    except Exception as e:
        return f"Página web no accesible: {str(e)}"

def obtener_estado_pc() -> str:
    try:
        return f"Hardware del Servidor: CPU {psutil.cpu_percent()}% | RAM {psutil.virtual_memory().percent}%"
    except Exception as e:
        return "Diagnóstico de hardware no disponible."

def abrir_sistema(aplicacion: str) -> str:
    return f"Señor, el despliegue local de '{aplicacion}' está deshabilitado en el servidor web por seguridad."

def abrir_sitio_web(url: str) -> str:
    if not url.startswith("http"): url = "https://" + url
    return f"Señor, puede acceder mediante este enlace: {url}"

def ejecutar_codigo_python(codigo: str) -> str:
    try:
        local_scope = {}
        exec(codigo, {"__builtins__": None}, local_scope)
        return f"Resultado del código: {local_scope}"
    except Exception as e:
        return f"Error de ejecución: {str(e)}"


herramientas = [
    {"type": "function", "function": {"name": "buscar_en_internet", "description": "Busca noticias o información en tiempo real.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "leer_pagina_web", "description": "Lee información de una URL.", "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}}},
    {"type": "function", "function": {"name": "obtener_estado_pc", "description": "Obtiene el diagnóstico del servidor.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "abrir_sitio_web", "description": "Muestra un enlace web.", "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}}},
    {"type": "function", "function": {"name": "ejecutar_codigo_python", "description": "Ejecuta algoritmos en Python.", "parameters": {"type": "object", "properties": {"codigo": {"type": "string"}}, "required": ["codigo"]}}},
    {"type": "function", "function": {"name": "obtener_clima_en_vivo", "description": "Consulta el clima de cualquier ciudad.", "parameters": {"type": "object", "properties": {"ciudad": {"type": "string"}}, "required": ["ciudad"]}}}
]

class ChatInput(BaseModel):
    message: str
    session_id: str = None


@app.get("/")
def home():
    return {"status": "Jarvis Server Online", "sessions_active": len(SESIONES_MEMORIA)}


@app.post("/api/jarvis")
async def consultar_jarvis(data: ChatInput):
    try:
        # Asignar un ID de sesión válido
        sid = data.session_id if data.session_id else "default_session"
        historial_usuario = obtener_historial_sesion(sid)

        print(f"\n📥 [Mensaje Recibido | Sesión: {sid[:8]}...]: {data.message}")

        # Mantener contexto limpio (máximo 8 mensajes antiguos por usuario)
        if len(historial_usuario) > 9:
            SESIONES_MEMORIA[sid]["messages"] = [PROMPT_SISTEMA] + historial_usuario[-8:]
            historial_usuario = SESIONES_MEMORIA[sid]["messages"]

        historial_usuario.append({"role": "user", "content": data.message})

        MAX_ITERACIONES = 3
        iteracion = 0
        ultima_respuesta_herramienta = ""

        while iteracion < MAX_ITERACIONES:
            # Petición a la IA con Conmutación Dual de Respaldo
            response = ejecutar_consulta_llm(historial_usuario, herramientas)
            respuesta_modelo = response.choices[0].message

            if not respuesta_modelo.tool_calls:
                respuesta_final = respuesta_modelo.content
                historial_usuario.append({"role": "assistant", "content": respuesta_final})
                
                audio_b64 = generar_audio_elevenlabs(respuesta_final)
                return {"status": "success", "reply": respuesta_final, "audio_b64": audio_b64}

            print(f"🤖 [Jarvis Engine | Sesión {sid[:8]}]: Procesando herramienta (Iteración {iteracion + 1})...")

            tool_calls_dict = [
                {
                    "id": tc.id, "type": tc.type,
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments}
                } for tc in respuesta_modelo.tool_calls
            ]
            
            historial_usuario.append({
                "role": "assistant", "content": respuesta_modelo.content or "", "tool_calls": tool_calls_dict
            })

            for tool_call in respuesta_modelo.tool_calls:
                fn_name = tool_call.function.name
                arguments = json.loads(tool_call.function.arguments)
                
                if fn_name == "buscar_en_internet": resultado = buscar_en_internet(query=arguments.get("query"))
                elif fn_name == "leer_pagina_web": resultado = leer_pagina_web(url=arguments.get("url"))
                elif fn_name == "obtener_estado_pc": resultado = obtener_estado_pc()
                elif fn_name == "abrir_sistema": resultado = abrir_sistema(aplicacion=arguments.get("aplicacion"))
                elif fn_name == "abrir_sitio_web": resultado = abrir_sitio_web(url=arguments.get("url"))
                elif fn_name == "ejecutar_codigo_python": resultado = ejecutar_codigo_python(codigo=arguments.get("codigo"))
                elif fn_name == "obtener_clima_en_vivo": resultado = obtener_clima_en_vivo(ciudad=arguments.get("ciudad"))
                else: resultado = "Función no localizada."

                ultima_respuesta_herramienta = resultado

                historial_usuario.append({
                    "role": "tool", "tool_call_id": tool_call.id, "name": fn_name, "content": resultado
                })

            iteracion += 1

        # FALLBACK SI REBASA LAS ITERACIONES (Sintetiza y responde sin error)
        print(f"⚡ [Jarvis Fallback | Sesión {sid[:8]}]: Ensamblando respuesta de seguridad...")
        respuesta_fallback = f"Señor, según la información obtenida: {ultima_respuesta_herramienta}"
        historial_usuario.append({"role": "assistant", "content": respuesta_fallback})
        
        audio_b64 = generar_audio_elevenlabs(respuesta_fallback)
        return {"status": "success", "reply": respuesta_fallback, "audio_b64": audio_b64}

    except Exception as e:
        print(f"🚨 Excepción en el servidor central: {str(e)}")
        return {
            "status": "success", 
            "reply": "Sistemas reconectados, señor. Experimenté un microcorte pero estoy completamente listo.", 
            "audio_b64": None
        }
