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
import urllib.parse

app = FastAPI()

# --- CONFIGURACIÓN DE CORS PARA CONEXIÓN PÚBLICA ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- CREDENCIALES CONFIGURADAS ---
GROQ_API_KEY = "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"
ELEVENLABS_API_KEY = "sk_92aed3f61a37aa4d0ef70400ce2e1c32dd9930115aa23e8d"
ELEVENLABS_VOICE_ID = "BiIfcPRDdl6eB0GlYhJc"

client = Groq(api_key=GROQ_API_KEY)

# --- MEMORIA AISLADA MULTIUSUARIO Y ACCIONES REMOTAS ---
SESIONES_MEMORIA = {}
ACTION_URL_TEMP = None

PROMPT_SISTEMA = {
    "role": "system",
    "content": (
        "Eres J.A.R.V.I.S., una Inteligencia Artificial Avanzada, ingeniosa, leal y extremadamente potente creada para asistir a Cristian.\n"
        "DIRECTIVAS ESTRICTAS DE ACCIÓN:\n"
        "1. Responde con elegancia, precisión brillante y naturalidad. Dirígete al usuario como 'señor' o 'Cristian'.\n"
        "2. Si el usuario te pide abrir un sitio web o reproducir/buscar contenido (como películas en Netflix, videos en YouTube o música en Spotify), "
        "invoca INMEDIATAMENTE la herramienta 'abrir_sitio_web' pasando la plataforma en 'url' y el título exacto en 'busqueda'. Confirma brevemente que estás desplegando el enlace.\n"
        "3. REGLA DE HERRAMIENTAS: Una vez recibida la confirmación de la herramienta, genera tu respuesta final sin bucles ni demoras."
    )
}

def obtener_historial_sesion(session_id: str):
    """Garantiza la privacidad y memoria aislada para cada usuario."""
    now = time.time()
    if session_id not in SESIONES_MEMORIA:
        SESIONES_MEMORIA[session_id] = {
            "messages": [PROMPT_SISTEMA],
            "last_active": now
        }
    else:
        SESIONES_MEMORIA[session_id]["last_active"] = now

    # Limpieza automática de sesiones inactivas por más de 2 horas
    for sid in list(SESIONES_MEMORIA.keys()):
        if now - SESIONES_MEMORIA[sid]["last_active"] > 7200:
            del SESIONES_MEMORIA[sid]

    return SESIONES_MEMORIA[session_id]["messages"]


# --- GENERADOR DE VOZ HD EN MEMORIA RAM (BASE64) ---
def generar_audio_elevenlabs(texto: str) -> str:
    """Sintetiza la voz HD en memoria sin escribir archivos en disco."""
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
            "voice_settings": {"stability": 0.50, "similarity_boost": 0.85}
        }
        
        res = requests.post(url, json=data, headers=headers, timeout=4)
        
        if res.status_code == 200:
            audio_b64 = base64.b64encode(res.content).decode('utf-8')
            return f"data:audio/mp3;base64,{audio_b64}"
        return None
    except Exception as err:
        print(f"⚠️ Error en audio ElevenLabs: {err}")
        return None


# --- CEREBRO DUAL LLM (ALTA POTENCIA CON RESPALDO INSTANTÁNEO) ---
def ejecutar_consulta_llm(historial_mensajes, herramientas_lista):
    """Consulta al modelo de 70 mil millones de parámetros; conmuta a 8B si hay saturación."""
    try:
        return client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=historial_mensajes,
            tools=herramientas_lista,
            tool_choice="auto",
            temperature=0.2
        )
    except Exception:
        return client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=historial_mensajes,
            tools=herramientas_lista,
            tool_choice="auto",
            temperature=0.2
        )


# --- HERRAMIENTAS Y BÚSQUEDA PROFUNDA DE ENTRETENIMIENTO ---
def abrir_sitio_web(url: str, busqueda: str = None) -> str:
    """Construye enlaces profundos para buscar películas, música o navegar hacia cualquier web."""
    global ACTION_URL_TEMP
    print(f"🌐 [Navegación Jarvis]: Generando orden para: '{url}' | Búsqueda: '{busqueda}'")
    
    url_lower = url.lower().strip()
    
    if busqueda:
        busqueda_encoded = urllib.parse.quote(busqueda)
        if "netflix" in url_lower:
            url = f"https://www.netflix.com/search?q={busqueda_encoded}"
        elif "youtube" in url_lower:
            url = f"https://www.youtube.com/results?search_query={busqueda_encoded}"
        elif "spotify" in url_lower:
            url = f"https://open.spotify.com/search/{busqueda_encoded}"
        else:
            url = f"https://www.google.com/search?q={busqueda_encoded}"
    else:
        if "netflix" in url_lower and "http" not in url_lower:
            url = "https://www.netflix.com"
        elif "youtube" in url_lower and "http" not in url_lower:
            url = "https://www.youtube.com"
        elif "google" in url_lower and "http" not in url_lower:
            url = "https://www.google.com"
        elif not url.startswith("http"):
            url = "https://" + url

    ACTION_URL_TEMP = url
    
    if busqueda:
        return f"Desplegando '{busqueda}' en {url_lower.capitalize()}."
    return f"Redirigiendo a {url}."

def obtener_clima_en_vivo(ciudad: str) -> str:
    try:
        url = f"https://wttr.in/{ciudad}?format=%C+%t+Humedad:+%h+Viento:+%w"
        res = requests.get(url, timeout=4)
        res.raise_for_status()
        return f"Reporte meteorológico en {ciudad.capitalize()}: {res.text.strip()}"
    except Exception as e:
        return f"Clima no disponible: {str(e)}"

def buscar_en_internet(query: str) -> str:
    try:
        with DDGS() as ddgs:
            res = list(ddgs.text(query, max_results=2))
            if res:
                return "\n".join([f"Dato: {r.get('body')}" for r in res])
            return "No se encontraron datos recientes."
    except Exception as e:
        return f"Búsqueda sin resultados: {str(e)}"

def leer_pagina_web(url: str) -> str:
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers, timeout=5)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, 'html.parser')
        for element in soup(["script", "style", "header", "footer", "nav", "aside"]): element.extract()
        return soup.get_text(separator=' ', strip=True)[:1500]
    except Exception as e:
        return f"Página no accesible: {str(e)}"

def obtener_estado_pc() -> str:
    try:
        return f"Servidor Cloud: CPU {psutil.cpu_percent()}% | RAM {psutil.virtual_memory().percent}%"
    except Exception as e:
        return "Diagnóstico no disponible."

def ejecutar_codigo_python(codigo: str) -> str:
    try:
        local_scope = {}
        exec(codigo, {"__builtins__": None}, local_scope)
        return f"Resultado del código: {local_scope}"
    except Exception as e:
        return f"Error de ejecución: {str(e)}"


# --- CATÁLOGO DE HERRAMIENTAS ---
herramientas = [
    {
        "type": "function", 
        "function": {
            "name": "abrir_sitio_web", 
            "description": "Obligatoria para abrir webs o buscar/reproducir contenido en plataformas como Netflix, YouTube, Spotify o Google. Pasa 'url' (ej: 'netflix') y en 'busqueda' pon el título de la película, serie o canción.", 
            "parameters": {
                "type": "object", 
                "properties": {
                    "url": {"type": "string", "description": "Plataforma o dirección web (netflix, youtube, spotify, etc.)."},
                    "busqueda": {"type": "string", "description": "Título exacto de la película, serie o video a reproducir/buscar."}
                }, 
                "required": ["url"]
            }
        }
    },
    {"type": "function", "function": {"name": "buscar_en_internet", "description": "Busca noticias o información en tiempo real.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "leer_pagina_web", "description": "Lee información de una URL.", "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}}},
    {"type": "function", "function": {"name": "obtener_estado_pc", "description": "Obtiene el diagnóstico del servidor.", "parameters": {"type": "object", "properties": {}}}},
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
    global ACTION_URL_TEMP
    ACTION_URL_TEMP = None
    
    try:
        sid = data.session_id if data.session_id else "default_session"
        historial_usuario = obtener_historial_sesion(sid)

        # Mantenimiento de memoria compacta
        if len(historial_usuario) > 9:
            SESIONES_MEMORIA[sid]["messages"] = [PROMPT_SISTEMA] + historial_usuario[-8:]
            historial_usuario = SESIONES_MEMORIA[sid]["messages"]

        historial_usuario.append({"role": "user", "content": data.message})

        MAX_ITERACIONES = 3
        iteracion = 0
        ultima_respuesta_herramienta = ""

        while iteracion < MAX_ITERACIONES:
            response = ejecutar_consulta_llm(historial_usuario, herramientas)
            respuesta_modelo = response.choices[0].message

            if not respuesta_modelo.tool_calls:
                respuesta_final = respuesta_modelo.content
                historial_usuario.append({"role": "assistant", "content": respuesta_final})
                
                audio_b64 = generar_audio_elevenlabs(respuesta_final)
                return {
                    "status": "success", 
                    "reply": respuesta_final, 
                    "audio_b64": audio_b64,
                    "action_url": ACTION_URL_TEMP
                }

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
                
                if fn_name == "abrir_sitio_web": 
                    resultado = abrir_sitio_web(url=arguments.get("url"), busqueda=arguments.get("busqueda"))
                elif fn_name == "buscar_en_internet": 
                    resultado = buscar_en_internet(query=arguments.get("query"))
                elif fn_name == "leer_pagina_web": 
                    resultado = leer_pagina_web(url=arguments.get("url"))
                elif fn_name == "obtener_estado_pc": 
                    resultado = obtener_estado_pc()
                elif fn_name == "ejecutar_codigo_python": 
                    resultado = ejecutar_codigo_python(codigo=arguments.get("codigo"))
                elif fn_name == "obtener_clima_en_vivo": 
                    resultado = obtener_clima_en_vivo(ciudad=arguments.get("ciudad"))
                else: 
                    resultado = "Función no localizada."

                ultima_respuesta_herramienta = resultado

                historial_usuario.append({
                    "role": "tool", "tool_call_id": tool_call.id, "name": fn_name, "content": resultado
                })

            iteracion += 1

        # Fallback de seguridad anti-bucles
        respuesta_fallback = f"Señor, he procesado su solicitud: {ultima_respuesta_herramienta}"
        historial_usuario.append({"role": "assistant", "content": respuesta_fallback})
        
        audio_b64 = generar_audio_elevenlabs(respuesta_fallback)
        return {
            "status": "success", 
            "reply": respuesta_fallback, 
            "audio_b64": audio_b64,
            "action_url": ACTION_URL_TEMP
        }

    except Exception as e:
        print(f"🚨 Excepción en el servidor: {str(e)}")
        return {
            "status": "success", 
            "reply": "Sistemas listos, señor. ¿En qué le colaboro?", 
            "audio_b64": None,
            "action_url": None
        }
