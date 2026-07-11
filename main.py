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

app = FastAPI()

# --- CONFIGURACIÓN DE CORS PARA PERMITIR PETICIONES DESDE GITHUB PAGES ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- CREDENCIALES ---
GROQ_API_KEY = "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" 
ELEVENLABS_API_KEY = "sk_92aed3f61a37aa4d0ef70400ce2e1c32dd9930115aa23e8d"
ELEVENLABS_VOICE_ID = "BiIfcPRDdl6eB0GlYhJc"

client = Groq(api_key=GROQ_API_KEY)


# --- GENERADOR DE VOZ HD EN MEMORIA RAM (BASE64) ---
def generar_audio_elevenlabs(texto: str) -> str:
    """Genera la voz HD de Jarvis en formato Base64 enviada en memoria RAM."""
    try:
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
        headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": ELEVENLABS_API_KEY
        }
        
        texto_limpio = re.sub(r'```[\s\S]*?```', '', texto)
        texto_limpio = re.sub(r'[*_#`]', '', texto_limpio)
        texto_limpio = texto_limpio.replace("\n", " ").strip()[:280]
        
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
        
        res = requests.post(url, json=data, headers=headers, timeout=5)
        
        if res.status_code == 200:
            audio_b64 = base64.b64encode(res.content).decode('utf-8')
            print("🎙️ [ElevenLabs]: Voz HD generada exitosamente.")
            return f"data:audio/mp3;base64,{audio_b64}"
        else:
            print(f"⚠️ Aviso ElevenLabs ({res.status_code}): {res.text}")
            return None

    except Exception as err:
        print(f"⚠️ Error temporal de audio: {err}")
        return None


# --- HERRAMIENTAS PÚBLICAS Y ADAPTADAS ---
def obtener_clima_en_vivo(ciudad: str) -> str:
    """Consulta el clima en vivo de cualquier ciudad."""
    print(f"🌤️ [Sistemas de Jarvis]: Sincronizando clima para: '{ciudad}'")
    try:
        url = f"https://wttr.in/{ciudad}?format=%C+%t+Humedad:+%h+Viento:+%w"
        res = requests.get(url, timeout=5)
        res.raise_for_status()
        return f"Reporte meteorológico actual en {ciudad.capitalize()}: {res.text.strip()}"
    except Exception as e:
        return f"No se pudo sincronizar el reporte del clima: {str(e)}"

def buscar_en_internet(query: str) -> str:
    """Realiza búsquedas en tiempo real en internet."""
    print(f"⚡ [Sistemas de Jarvis]: Buscando en la red: '{query}'")
    try:
        with DDGS() as ddgs:
            res = list(ddgs.text(query, max_results=3))
            if res:
                return "\n".join([f"Título: {r.get('title')}\nURL: {r.get('href')}\nResumen: {r.get('body')}\n" for r in res])
            return "No se encontraron resultados relevantes."
    except Exception as e:
        return f"Error de red: {str(e)}"

def leer_pagina_web(url: str) -> str:
    """Lee el texto plano de una URL requerida."""
    print(f"📖 [Sistemas de Jarvis]: Leyendo sitio web: '{url}'")
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers, timeout=6)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, 'html.parser')
        for element in soup(["script", "style", "header", "footer", "nav", "aside"]): element.extract()
        return soup.get_text(separator=' ', strip=True)[:3000]
    except Exception as e:
        return f"No se pudo leer la página web: {str(e)}"

def obtener_estado_pc() -> str:
    """Diagnóstico de uso de CPU y RAM del servidor en la nube."""
    try:
        return f"Diagnóstico de Hardware del Servidor:\n- Uso de CPU: {psutil.cpu_percent(interval=0.5)}%\n- Uso de Memoria RAM: {psutil.virtual_memory().percent}%"
    except Exception as e:
        return f"Error en el escáner de hardware: {str(e)}"

def abrir_sistema(aplicacion: str) -> str:
    """Respuesta protegida para la versión web."""
    return f"Señor, el despliegue de aplicaciones locales ({aplicacion}) está desactivado en la versión web para proteger la seguridad del servidor."

def abrir_sitio_web(url: str) -> str:
    """Muestra el enlace para el usuario."""
    if not url.startswith("http"): url = "https://" + url
    return f"Señor, puede acceder al sitio desde este enlace: {url}"

def ejecutar_codigo_python(codigo: str) -> str:
    """Ejecuta algoritmos sencillos directamente."""
    try:
        # Ejecución restringida y rápida en memoria
        local_scope = {}
        exec(codigo, {"__builtins__": None}, local_scope)
        return f"EJECUCIÓN EXITOSA. Variables resultantes: {local_scope}"
    except Exception as e:
        return f"ERROR DE EJECUCIÓN: {str(e)}"


# --- CATÁLOGO DE HERRAMIENTAS ---
herramientas = [
    {"type": "function", "function": {"name": "buscar_en_internet", "description": "Busca noticias o datos en internet.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "leer_pagina_web", "description": "Lee el contenido de una URL específica.", "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}}},
    {"type": "function", "function": {"name": "obtener_estado_pc", "description": "Obtiene el diagnóstico de CPU y RAM del servidor.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "abrir_sistema", "description": "Avisa que las apps locales no están disponibles en la nube.", "parameters": {"type": "object", "properties": {"aplicacion": {"type": "string"}}, "required": ["aplicacion"]}}},
    {"type": "function", "function": {"name": "abrir_sitio_web", "description": "Genera el enlace hacia una web.", "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}}},
    {"type": "function", "function": {"name": "ejecutar_codigo_python", "description": "Ejecuta algoritmos de Python.", "parameters": {"type": "object", "properties": {"codigo": {"type": "string"}}, "required": ["codigo"]}}},
    {"type": "function", "function": {"name": "obtener_clima_en_vivo", "description": "Consulta el clima actual de cualquier ciudad.", "parameters": {"type": "object", "properties": {"ciudad": {"type": "string"}}, "required": ["ciudad"]}}}
]

class ChatInput(BaseModel):
    message: str

HISTORIAL_CONVERSACION = [
    {
        "role": "system",
        "content": (
            "Eres J.A.R.V.I.S., la inteligencia artificial avanzada creada por Tony Stark para asistir a Cristian.\n"
            "DIRECTIVA DE PERSONALIDAD:\n"
            "1. Tu estilo es elegante, ingenioso, leal, sofisticado y eficiente, exactamente como en las películas de Iron Man.\n"
            "2. Responde de forma concisa, inteligente y natural. Dirígete al usuario como 'señor' o 'Cristian'.\n"
            "3. Entiendes modismos y saludos informales ('qué ondas', 'de una', 'todo bien'), respondiendo con una actitud calmada y genial."
        )
    }
]

@app.get("/")
def home():
    return {"status": "Jarvis Server Online"}

@app.post("/api/jarvis")
async def consultar_jarvis(data: ChatInput):
    global HISTORIAL_CONVERSACION
    try:
        print(f"\n📥 [Mensaje Recibido]: {data.message}")
        HISTORIAL_CONVERSACION.append({"role": "user", "content": data.message})

        MAX_ITERACIONES = 5
        iteracion = 0

        while iteracion < MAX_ITERACIONES:
            response = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=HISTORIAL_CONVERSACION[-10:],
                tools=herramientas,
                tool_choice="auto",
                temperature=0.2
            )

            respuesta_modelo = response.choices[0].message

            if not respuesta_modelo.tool_calls:
                respuesta_final = respuesta_modelo.content
                HISTORIAL_CONVERSACION.append({"role": "assistant", "content": respuesta_final})
                
                audio_b64 = generar_audio_elevenlabs(respuesta_final)
                
                return {"status": "success", "reply": respuesta_final, "audio_b64": audio_b64}

            tool_calls_dict = [
                {
                    "id": tc.id, "type": tc.type,
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments}
                } for tc in respuesta_modelo.tool_calls
            ]
            
            HISTORIAL_CONVERSACION.append({
                "role": "assistant", "content": respuesta_modelo.content, "tool_calls": tool_calls_dict
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
                else: resultado = "Función no reconocida."

                HISTORIAL_CONVERSACION.append({
                    "role": "tool", "tool_call_id": tool_call.id, "name": fn_name, "content": resultado
                })

            iteracion += 1
        return {"status": "error", "reply": "Límite de iteraciones alcanzado."}
    except Exception as e:
        print(f"🚨 Error en el servidor central: {str(e)}")
        return {"status": "error", "reply": f"Fallo del sistema central: {str(e)}"}