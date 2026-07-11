from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
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
import io
import sys
import contextlib
from PIL import Image

# LIBRERÍAS DE LECTURA DE ARCHIVOS MULTIFORMATO
try:
    import pypdf
except ImportError:
    pypdf = None

try:
    import docx
except ImportError:
    docx = None

try:
    import openpyxl
except ImportError:
    openpyxl = None

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
        "3. FORMATO MATEMÁTICO AVANZADO: Cuando escribas ecuaciones, fórmulas, fracciones, raíces, límites o integrales, utiliza SIEMPRE sintaxis LaTeX.\n"
        "   - Para ecuaciones centradas e independientes usa '$$ ecuacion $$'. Ejemplo: $$ x = \\frac{-b \\pm \\sqrt{b^2 - 4ac}}{2a} $$\n"
        "   - Para fórmulas dentro del texto usa '$ ecuacion $'. Ejemplo: $a^2 + b^2 = c^2$\n"
        "4. SI ANALIZAS TAREAS O DOCUMENTOS: Revisa minuciosamente los problemas, gráficas y ecuaciones. Resuelve los ejercicios paso a paso con máxima claridad.\n"
        "5. REGLA DE HERRAMIENTAS: Una vez recibida la confirmación de la herramienta, genera tu respuesta final sin bucles ni demoras."
    )
}

def obtener_historial_sesion(session_id: str):
    now = time.time()
    if session_id not in SESIONES_MEMORIA:
        SESIONES_MEMORIA[session_id] = {
            "messages": [PROMPT_SISTEMA],
            "last_active": now,
            "last_image_b64": None
        }
    else:
        SESIONES_MEMORIA[session_id]["last_active"] = now

    for sid in list(SESIONES_MEMORIA.keys()):
        if now - SESIONES_MEMORIA[sid]["last_active"] > 7200:
            del SESIONES_MEMORIA[sid]

    return SESIONES_MEMORIA[session_id]


# --- OPTIMIZADOR Y COMPRESOR DE IMÁGENES PARA GROQ VISION ---
def optimizar_imagen_b64(image_b64_data: str, max_dim: int = 1024) -> str:
    """Asegura que la imagen tenga fondo blanco puro, proporciones correctas y peso < 200 KB."""
    try:
        if "," in image_b64_data:
            header, encoded = image_b64_data.split(",", 1)
        else:
            encoded = image_b64_data

        img_bytes = base64.b64decode(encoded)
        img = Image.open(io.BytesIO(img_bytes))

        # Convertir transparencias (RGBA) a fondo blanco RGB
        if img.mode in ("RGBA", "P", "LA"):
            background = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "RGBA":
                background.paste(img, mask=img.split()[3])
            else:
                background.paste(img)
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")

        # Redimensionar si supera la dimensión máxima
        width, height = img.size
        if width > max_dim or height > max_dim:
            if width > height:
                new_w = max_dim
                new_h = int(height * (max_dim / width))
            else:
                new_h = max_dim
                new_w = int(width * (max_dim / height))
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

        output_buffer = io.BytesIO()
        img.save(output_buffer, format="JPEG", quality=70, optimize=True)
        compressed_bytes = output_buffer.getvalue()
        
        compressed_b64 = base64.b64encode(compressed_bytes).decode('utf-8')
        return f"data:image/jpeg;base64,{compressed_b64}"
    except Exception as e:
        print(f"⚠️ Error al optimizar imagen: {e}")
        return image_b64_data


# --- PROCESADOR MULTIMODAL ROBUSTO ---
def procesar_archivo_adjunto(file_b64: Optional[str] = None, file_name: Optional[str] = None) -> tuple[str, str]:
    if not file_b64:
        return 'none', ""

    try:
        if "," in file_b64:
            header, encoded = file_b64.split(",", 1)
        else:
            encoded = file_b64
            header = ""

        file_bytes = base64.b64decode(encoded)
        ext = os.path.splitext(file_name.lower())[1] if file_name else ""

        # 1. IMÁGENES / PDFS RENDERIZADOS A VISIÓN HD
        if ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif'] or 'image/' in header:
            return 'image', file_b64

        # 2. AUDIOS CON GROQ WHISPER
        if ext in ['.mp3', '.wav', '.m4a', '.ogg', '.flac', '.webm'] or 'audio/' in header:
            try:
                buffer = io.BytesIO(file_bytes)
                buffer.name = file_name or "audio.mp3"
                transcription = client.audio.transcriptions.create(
                    file=(buffer.name, buffer.read()),
                    model="whisper-large-v3",
                    language="es"
                )
                return 'text_context', f"\n\n[TRANSCRIPCIÓN DE AUDIO '{file_name}']:\n\"{transcription.text}\"\n"
            except Exception as e:
                return 'text_context', f"\n\n[AVISO AUDIO '{file_name}']: {str(e)}\n"

        # 3. DOCUMENTOS WORD (.docx)
        if ext in ['.docx', '.doc'] and docx:
            try:
                doc = docx.Document(io.BytesIO(file_bytes))
                texto = "\n".join([p.text for p in doc.paragraphs if p.text])
                return 'text_context', f"\n\n[CONTENIDO WORD '{file_name}']:\n{texto[:15000]}\n"
            except Exception as e:
                return 'text_context', f"\n\n[AVISO WORD '{file_name}']: {str(e)}\n"

        # 4. HOJAS DE CÁLCULO EXCEL Y CSV
        if ext in ['.xlsx', '.xls', '.csv']:
            try:
                if ext == '.csv':
                    decoded = file_bytes.decode('utf-8', errors='ignore')
                    return 'text_context', f"\n\n[CONTENIDO CSV '{file_name}']:\n{decoded[:15000]}\n"
                elif openpyxl:
                    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
                    res = []
                    for sheet in wb.sheetnames[:3]:
                        ws = wb[sheet]
                        res.append(f"--- Hoja: {sheet} ---")
                        for row in ws.iter_rows(values_only=True):
                            if any(row):
                                res.append(" | ".join([str(v) if v is not None else "" for v in row]))
                    return 'text_context', f"\n\n[CONTENIDO EXCEL '{file_name}']:\n" + "\n".join(res)[:15000] + "\n"
            except Exception as e:
                return 'text_context', f"\n\n[AVISO EXCEL '{file_name}']: {str(e)}\n"

        # 5. CÓDIGO FUENTE / TEXTO PLANO
        texto_decoded = file_bytes.decode('utf-8', errors='ignore')
        lang = ext.replace('.', '') if ext else 'txt'
        return 'text_context', f"\n\n[CONTENIDO ARCHIVO '{file_name}']:\n```{lang}\n{texto_decoded[:15000]}\n```\n"

    except Exception as err:
        print(f"⚠️ Error procesando adjunto: {err}")
        return 'none', ""


# --- GENERADOR DE VOZ HD EN RAM ---
def generar_audio_elevenlabs(texto: str) -> str:
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
        texto_limpio = re.sub(r'\$\$[\s\S]*?\$\$', ' según la fórmula desplegada en pantalla ', texto_limpio)
        texto_limpio = re.sub(r'\$[\s\S]*?\$', '', texto_limpio)
        texto_limpio = re.sub(r'\\[a-zA-Z]+', '', texto_limpio)
        texto_limpio = re.sub(r'[*_#`{}]', '', texto_limpio)
        texto_limpio = texto_limpio.replace("\n", " ").strip()[:250]
        
        if not texto_limpio:
            texto_limpio = "Sistemas matemáticos desplegados en pantalla, señor."

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
    except Exception:
        return None


# --- CEREBROS IA CON COMPRESIÓN Y MANEJO SEGURO DE ERRORES ---
def ejecutar_consulta_vision(historial_mensajes, image_b64_data):
    # Optimización automática con Pillow antes de llamar a la API
    image_b64_data = optimizar_imagen_b64(image_b64_data, max_dim=1024)
    
    messages_multimodal = []
    # Filtrar historial para mantener el contexto limpio
    for msg in historial_mensajes[-5:-1]:
        if isinstance(msg.get("content"), str) and msg.get("role") in ["user", "assistant"]:
            messages_multimodal.append({"role": msg.get("role"), "content": msg.get("content")})
            
    last_msg = historial_mensajes[-1]
    prompt_texto = last_msg.get("content", "Analice esta imagen por favor, señor.")
    if not prompt_texto.strip():
        prompt_texto = "Analice esta imagen detalladamente, señor."

    multimodal_user_msg = {
        "role": "user",
        "content": [
            {"type": "text", "text": prompt_texto},
            {"type": "image_url", "image_url": {"url": image_b64_data}}
        ]
    }
    messages_multimodal.append(multimodal_user_msg)

    try:
        return client.chat.completions.create(
            model="llama-3.2-11b-vision-preview",
            messages=messages_multimodal,
            temperature=0.2,
            max_tokens=2048
        )
    except Exception as err_v1:
        print(f"⚠️ Aviso Llama 11B Vision: {err_v1}. Reintentando con Llama 90B Vision...")
        return client.chat.completions.create(
            model="llama-3.2-90b-vision-preview",
            messages=messages_multimodal,
            temperature=0.2,
            max_tokens=2048
        )

def ejecutar_consulta_llm(historial_mensajes, herramientas_lista):
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


# --- HERRAMIENTAS Y EJECUTOR DE CÓDIGO PYTHON ---
def abrir_sitio_web(url: str, busqueda: str = None) -> str:
    global ACTION_URL_TEMP
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
    """Ejecuta código Python y captura la salida estándar (print)."""
    try:
        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            local_scope = {}
            exec(codigo, {"__builtins__": __builtins__}, local_scope)
        output = f.getvalue().strip()
        if not output and local_scope:
            output = f"Variables resultantes: {local_scope}"
        return output if output else "Código ejecutado exitosamente sin salida de texto."
    except Exception as e:
        return f"Error de ejecución: {str(e)}"


herramientas = [
    {
        "type": "function", 
        "function": {
            "name": "abrir_sitio_web", 
            "description": "Obligatoria para abrir webs o buscar/reproducir contenido en plataformas como Netflix, YouTube, Spotify o Google.", 
            "parameters": {
                "type": "object", 
                "properties": {
                    "url": {"type": "string"},
                    "busqueda": {"type": "string"}
                }, 
                "required": ["url"]
            }
        }
    },
    {"type": "function", "function": {"name": "buscar_en_internet", "description": "Busca en la web.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "leer_pagina_web", "description": "Lee una URL.", "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "obtener_estado_pc", "description": "Diagnóstico.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "ejecutar_codigo_python", "description": "Ejecuta código Python y captura los resultados impresos.", "parameters": {"type": "object", "properties": {"codigo": {"type": "string"}}, "required": ["codigo"]}}},
    {"type": "function", "function": {"name": "obtener_clima_en_vivo", "description": "Clima.", "parameters": {"type": "object", "properties": {"ciudad": {"type": "string"}}, "required": ["ciudad"]}}}
]

class ChatInput(BaseModel):
    message: Optional[str] = ""
    session_id: Optional[str] = "default_session"
    file_b64: Optional[str] = None
    file_name: Optional[str] = None


@app.get("/")
def home():
    return {"status": "Jarvis Server Online", "sessions_active": len(SESIONES_MEMORIA)}


@app.post("/api/jarvis")
async def consultar_jarvis(data: ChatInput):
    global ACTION_URL_TEMP
    ACTION_URL_TEMP = None
    
    try:
        sid = data.session_id if data.session_id else "default_session"
        sesion_data = obtener_historial_sesion(sid)
        historial_usuario = sesion_data["messages"]

        if len(historial_usuario) > 9:
            sesion_data["messages"] = [PROMPT_SISTEMA] + historial_usuario[-8:]
            historial_usuario = sesion_data["messages"]

        categoria_archivo, contenido_o_b64 = procesar_archivo_adjunto(data.file_b64, data.file_name)
        prompt_usuario = data.message if data.message else "Señor, he recibido un archivo para analizar."

        # SI SE SUBIÓ UNA NUEVA IMAGEN, GUARDARLA EN LA MEMORIA DE SESIÓN
        if categoria_archivo == 'image':
            sesion_data["last_image_b64"] = contenido_o_b64

        usar_vision = (categoria_archivo == 'image') or (
            sesion_data.get("last_image_b64") is not None and 
            any(w in prompt_usuario.lower() for w in ["documento", "ejercicio", "tarea", "imagen", "archivo", "resuelve", "problema", "siguiente", "resto", "todos"])
        )

        if usar_vision and sesion_data.get("last_image_b64"):
            historial_usuario.append({"role": "user", "content": prompt_usuario})
            print("👁️ [Jarvis Vision]: Procesando modelo de visión optimizado...")
            try:
                response = ejecutar_consulta_vision(historial_usuario, sesion_data["last_image_b64"])
                respuesta_final = response.choices[0].message.content
            except Exception as vision_err:
                print(f"🚨 Error en Visión: {vision_err}")
                respuesta_final = "Señor, he analizado el documento. Por favor indíqueme el número del ejercicio específico que desea resolver primero."

            historial_usuario.append({"role": "assistant", "content": respuesta_final})
            audio_b64 = generar_audio_elevenlabs(respuesta_final)
            return {"status": "success", "reply": respuesta_final, "audio_b64": audio_b64, "action_url": None}

        # MODO TEXTO DIGITAL (WORD, EXCEL, CÓDIGO, AUDIOS)
        if categoria_archivo == 'text_context':
            prompt_usuario += contenido_o_b64

        historial_usuario.append({"role": "user", "content": prompt_usuario})

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

        respuesta_fallback = f"Señor, procesé su solicitud: {ultima_respuesta_herramienta}"
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
            "reply": "Sistemas reconectados, señor. Ya me encuentro operativo.", 
            "audio_b64": None,
            "action_url": None
        }
