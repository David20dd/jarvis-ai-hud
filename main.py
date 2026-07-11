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
import io

# LIBRERÍAS DE LECTURA DE ARCHIVOS MULTIFORMATO
import pypdf
import docx
import openpyxl

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
        "3. Tienes la habilidad de analizar todo tipo de archivos (imágenes, PDFs, documentos Word, hojas de cálculo Excel, scripts de código y audios). "
        "Sé minucioso, profesional y directo al responder sobre el contenido de los archivos adjuntos.\n"
        "4. REGLA DE HERRAMIENTAS: Una vez recibida la confirmación de la herramienta, genera tu respuesta final sin bucles ni demoras."
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

    for sid in list(SESIONES_MEMORIA.keys()):
        if now - SESIONES_MEMORIA[sid]["last_active"] > 7200:
            del SESIONES_MEMORIA[sid]

    return SESIONES_MEMORIA[session_id]["messages"]


# --- MOTOR DE EXTRACCIÓN Y PROCESAMIENTO DE ARCHIVOS MULTIFORMATO ---
def procesar_archivo_adjunto(file_b64: str, file_name: str) -> tuple[str, str]:
    """
    Procesa cualquier tipo de archivo enviado en Base64.
    Retorna: (categoria, contenido_extraido)
    Categorías posibles: 'image', 'text_context'
    """
    if not file_b64:
        return 'none', ""

    if "," in file_b64:
        header, encoded = file_b64.split(",", 1)
    else:
        encoded = file_b64
        header = ""

    file_bytes = base64.b64decode(encoded)
    ext = os.path.splitext(file_name.lower())[1] if file_name else ""

    # 1. IMÁGENES
    if ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif'] or 'image/' in header:
        return 'image', file_b64

    # 2. AUDIOS (TRANSCRIPCIÓN EN TIEMPO REAL CON GROQ WHISPER)
    if ext in ['.mp3', '.wav', '.m4a', '.ogg', '.flac', '.webm'] or 'audio/' in header:
        try:
            buffer = io.BytesIO(file_bytes)
            buffer.name = file_name or "audio_usuario.mp3"
            transcription = client.audio.transcriptions.create(
                file=(buffer.name, buffer.read()),
                model="whisper-large-v3",
                language="es"
            )
            return 'text_context', f"\n\n[TRANSCRIPCIÓN DE AUDIO ADJUNTO '{file_name}']:\n\"{transcription.text}\"\n"
        except Exception as e:
            return 'text_context', f"\n\n[ERROR AL PROCESAR AUDIO '{file_name}']: {str(e)}\n"

    # 3. DOCUMENTOS PDF
    if ext == '.pdf' or 'application/pdf' in header:
        try:
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            texto = ""
            for i, page in enumerate(reader.pages):
                t = page.extract_text()
                if t: texto += f"\n--- Página {i+1} ---\n" + t
            return 'text_context', f"\n\n[CONTENIDO DEL DOCUMENTO PDF '{file_name}']:\n{texto[:15000]}\n"
        except Exception as e:
            return 'text_context', f"\n\n[ERROR AL LEER PDF '{file_name}']: {str(e)}\n"

    # 4. DOCUMENTOS WORD (.docx)
    if ext in ['.docx', '.doc'] or 'wordprocessingml' in header:
        try:
            doc = docx.Document(io.BytesIO(file_bytes))
            texto = "\n".join([p.text for p in doc.paragraphs if p.text])
            return 'text_context', f"\n\n[CONTENIDO DEL DOCUMENTO WORD '{file_name}']:\n{texto[:15000]}\n"
        except Exception as e:
            return 'text_context', f"\n\n[ERROR AL LEER DOCUMENTO WORD '{file_name}']: {str(e)}\n"

    # 5. HOJAS DE CÁLCULO EXCEL Y CSV (.xlsx, .csv)
    if ext in ['.xlsx', '.xls', '.csv']:
        try:
            if ext == '.csv':
                decoded = file_bytes.decode('utf-8', errors='ignore')
                return 'text_context', f"\n\n[CONTENIDO DE HOJA DE CÁLCULO CSV '{file_name}']:\n{decoded[:15000]}\n"
            else:
                wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
                res = []
                for sheet in wb.sheetnames:
                    ws = wb[sheet]
                    res.append(f"--- Hoja: {sheet} ---")
                    for row in ws.iter_rows(values_only=True):
                        if any(row):
                            res.append(" | ".join([str(v) if v is not None else "" for v in row]))
                return 'text_context', f"\n\n[CONTENIDO DE HOJA DE CÁLCULO EXCEL '{file_name}']:\n" + "\n".join(res)[:15000] + "\n"
        except Exception as e:
            return 'text_context', f"\n\n[ERROR AL LEER EXCEL '{file_name}']: {str(e)}\n"

    # 6. TEXTO PLANO / CÓDIGO FUENTE (py, js, html, css, json, sql, txt, md, etc.)
    try:
        texto_decoded = file_bytes.decode('utf-8', errors='ignore')
        lang = ext.replace('.', '') if ext else 'txt'
        return 'text_context', f"\n\n[CONTENIDO DEL ARCHIVO ADJUNTO '{file_name}']:\n```{lang}\n{texto_decoded[:15000]}\n```\n"
    except Exception as e:
        return 'text_context', f"\n\n[ERROR AL LEER ARCHIVO '{file_name}']: {str(e)}\n"


# --- GENERADOR DE VOZ HD EN MEMORIA RAM ---
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


# --- CEREBROS IA (VISIÓN Y TEXTO) ---
def ejecutar_consulta_vision(historial_mensajes, image_b64_data):
    if not image_b64_data.startswith("data:image"):
        image_b64_data = f"data:image/jpeg;base64,{image_b64_data}"
    
    messages_multimodal = []
    for msg in historial_mensajes[:-1]:
        if isinstance(msg.get("content"), str):
            messages_multimodal.append(msg)
            
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
            temperature=0.2
        )
    except Exception:
        return client.chat.completions.create(
            model="llama-3.2-90b-vision-preview",
            messages=messages_multimodal,
            temperature=0.2
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


# --- HERRAMIENTAS ---
def abrir_sitio_web(url: str, busqueda: str = None) -> str:
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
    file_b64: str = None
    file_name: str = None


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

        if len(historial_usuario) > 9:
            SESIONES_MEMORIA[sid]["messages"] = [PROMPT_SISTEMA] + historial_usuario[-8:]
            historial_usuario = SESIONES_MEMORIA[sid]["messages"]

        # === PROCESAMIENTO DE ARCHIVO MULTIFORMATO ===
        categoria_archivo, contenido_extraido = procesar_archivo_adjunto(data.file_b64, data.file_name)

        prompt_usuario = data.message if data.message else "Señor, analice el archivo adjunto por favor."

        # SI ES IMAGEN -> MODO VISIÓN ARTIFICIAL
        if categoria_archivo == 'image':
            historial_usuario.append({"role": "user", "content": prompt_usuario})
            print(f"👁️ [Jarvis Vision]: Analizando imagen '{data.file_name}'...")
            response = ejecutar_consulta_vision(historial_usuario, data.file_b64)
            respuesta_final = response.choices[0].message.content
            
            historial_usuario.append({"role": "assistant", "content": respuesta_final})
            audio_b64 = generar_audio_elevenlabs(respuesta_final)
            return {"status": "success", "reply": respuesta_final, "audio_b64": audio_b64, "action_url": None}

        # SI ES DOCUMENTO, EXCEL, AUDIO O CÓDIGO -> MODO TEXTO INYECTADO
        if categoria_archivo == 'text_context':
            prompt_usuario += contenido_extraido

        historial_usuario.append({"role": "user", "content": prompt_usuario})

        # === PROCESAMIENTO GENERAL CON LLAMA 3.3 70B ===
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
