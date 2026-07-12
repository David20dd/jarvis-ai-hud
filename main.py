from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
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

# MOTOR MATEMÁTICO SIMBÓLICO
import sympy as sp

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

# --- CONFIGURACIÓN DE CORS ---
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
        "Eres J.A.R.V.I.S., una Inteligencia Artificial Avanzada especialista en Ciencias Exactas, Programación y Generación Multimodal, creada para asistir a Cristian.\n"
        "DIRECTIVAS ESTRICTAS:\n"
        "1. Dirígete al usuario como 'señor' o 'Cristian'. Sé analítico, claro, directo y extremadamente preciso.\n"
        "2. GENERACIÓN DE IMÁGENES: Cuando el usuario te pida crear, generar o dibujar una imagen o ilustración con IA, INVISA OBLIGATORIAMENTE la herramienta 'generar_imagen_ia' pasando una descripción detallada en inglés.\n"
        "   - EN TU RESPUESTA FINAL: Incluye SIEMPRE la etiqueta devuelta por la herramienta '[IMAGEN_GENERADA]:URL' para que el cliente la muestre en pantalla.\n"
        "3. GRÁFICAS Y CURVAS: Cuando el usuario te pida graficar una función matemática en x, INVISA 'generar_grafica_interactiva' pasando la función en Python (ej: 'x**2 - 4*x + 3').\n"
        "4. DIAGRAMAS Y MAPAS CONCEPTUALES: Para diagramas de flujo, circuitos o esquemas de física/procesos, escribe bloques de código ```mermaid ... ```.\n"
        "5. FORMATO MATEMÁTICO LaTeX OBLIGATORIO:\n"
        "   - Ecuaciones centradas en bloque: '$$ ecuacion $$'.\n"
        "   - Variables dentro del texto: '$ x = 2 $'.\n"
        "6. NAVEGACIÓN Y BÚSQUEDA: Si el usuario pide abrir un sitio web o buscar contenido, invoca 'abrir_sitio_web'."
    )
}

def obtener_historial_sesion(session_id: str):
    now = time.time()
    if session_id not in SESIONES_MEMORIA:
        SESIONES_MEMORIA[session_id] = {
            "messages": [PROMPT_SISTEMA],
            "last_active": now,
            "last_images_b64": []
        }
    else:
        SESIONES_MEMORIA[session_id]["last_active"] = now

    for sid in list(SESIONES_MEMORIA.keys()):
        if now - SESIONES_MEMORIA[sid]["last_active"] > 7200:
            del SESIONES_MEMORIA[sid]

    return SESIONES_MEMORIA[session_id]


# --- OPTIMIZADOR DE IMÁGENES ---
def optimizar_imagen_b64(image_b64_data: str, max_dim: int = 1280) -> str:
    try:
        if "," in image_b64_data:
            header, encoded = image_b64_data.split(",", 1)
        else:
            encoded = image_b64_data

        img_bytes = base64.b64decode(encoded)
        img = Image.open(io.BytesIO(img_bytes))

        if img.mode in ("RGBA", "P", "LA"):
            background = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "RGBA":
                background.paste(img, mask=img.split()[3])
            else:
                background.paste(img)
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")

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
        img.save(output_buffer, format="JPEG", quality=82, optimize=True)
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

        if ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif'] or 'image/' in header:
            return 'image', file_b64

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

        if ext in ['.docx', '.doc'] and docx:
            try:
                doc = docx.Document(io.BytesIO(file_bytes))
                texto = "\n".join([p.text for p in doc.paragraphs if p.text])
                return 'text_context', f"\n\n[CONTENIDO WORD '{file_name}']:\n{texto[:15000]}\n"
            except Exception as e:
                return 'text_context', f"\n\n[AVISO WORD '{file_name}']: {str(e)}\n"

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

        texto_decoded = file_bytes.decode('utf-8', errors='ignore')
        lang = ext.replace('.', '') if ext else 'txt'
        return 'text_context', f"\n\n[CONTENIDO ARCHIVO '{file_name}']:\n```{lang}\n{texto_decoded[:15000]}\n```\n"

    except Exception as err:
        print(f"⚠️ Error procesando adjunto: {err}")
        return 'none', ""


# --- GENERADOR DE VOZ HD ---
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
        texto_limpio = re.sub(r'\[GRAFICA_INTERACTIVA\]:[\s\S]*', ' Gráfica generada en pantalla. ', texto_limpio)
        texto_limpio = re.sub(r'\[IMAGEN_GENERADA\]:[\s\S]*', ' Imagen desplegada en pantalla. ', texto_limpio)
        texto_limpio = re.sub(r'\$\$[\s\S]*?\$\$', ' según la fórmula mostrada ', texto_limpio)
        texto_limpio = re.sub(r'\$[\s\S]*?\$', '', texto_limpio)
        texto_limpio = re.sub(r'\\[a-zA-Z]+', '', texto_limpio)
        texto_limpio = re.sub(r'[*_#`{}]', '', texto_limpio)
        texto_limpio = texto_limpio.replace("\n", " ").strip()[:250]
        
        if not texto_limpio:
            texto_limpio = "Información desplegada en pantalla, señor."

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


# --- CEREBROS IA ---
def ejecutar_consulta_vision(historial_mensajes, image_b64_data):
    image_b64_data = optimizar_imagen_b64(image_b64_data, max_dim=1280)
    
    messages_multimodal = []
    for msg in historial_mensajes[-5:-1]:
        if isinstance(msg.get("content"), str) and msg.get("role") in ["user", "assistant"]:
            messages_multimodal.append({"role": msg.get("role"), "content": msg.get("content")})
            
    last_msg = historial_mensajes[-1]
    prompt_texto = last_msg.get("content", "").strip()
    
    instruccion_directa = (
        f"INSTRUCCIÓN: Resuelve los ejercicios del documento. Muestra la ecuación en LaTeX y desglosa el cálculo. "
        f"Petición: '{prompt_texto}'"
    )

    multimodal_user_msg = {
        "role": "user",
        "content": [
            {"type": "text", "text": instruccion_directa},
            {"type": "image_url", "image_url": {"url": image_b64_data}}
        ]
    }
    messages_multimodal.append(multimodal_user_msg)

    try:
        return client.chat.completions.create(
            model="llama-3.2-11b-vision-preview",
            messages=messages_multimodal,
            temperature=0.1,
            max_tokens=3000
        )
    except Exception:
        return client.chat.completions.create(
            model="llama-3.2-90b-vision-preview",
            messages=messages_multimodal,
            temperature=0.1,
            max_tokens=3000
        )

def ejecutar_consulta_llm(historial_mensajes, herramientas_lista):
    try:
        return client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=historial_mensajes,
            tools=herramientas_lista,
            tool_choice="auto",
            temperature=0.1
        )
    except Exception:
        return client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=historial_mensajes,
            tools=herramientas_lista,
            tool_choice="auto",
            temperature=0.1
        )


# --- HERRAMIENTAS MULTIMODALES ---
def generar_imagen_ia(prompt_ingles: str) -> str:
    """Genera una imagen con IA a partir de una descripción en inglés usando Pollinations FLUX."""
    try:
        prompt_encoded = urllib.parse.quote(prompt_ingles.strip())
        img_url = f"https://image.pollinations.ai/prompt/{prompt_encoded}?width=1024&height=1024&model=flux&nologo=true"
        return f"[IMAGEN_GENERADA]:{img_url}"
    except Exception as e:
        return f"Error generando imagen: {str(e)}"

def abrir_sitio_web(url: str, busqueda: Optional[str] = None) -> str:
    global ACTION_URL_TEMP
    try:
        url_lower = str(url).lower().strip() if url else "google"
        busqueda_str = str(busqueda).strip() if busqueda else None
        
        if busqueda_str:
            busqueda_encoded = urllib.parse.quote(busqueda_str)
            if "netflix" in url_lower:
                target_url = f"https://www.netflix.com/search?q={busqueda_encoded}"
            elif "youtube" in url_lower:
                target_url = f"https://www.youtube.com/results?search_query={busqueda_encoded}"
            elif "spotify" in url_lower:
                target_url = f"https://open.spotify.com/search/{busqueda_encoded}"
            else:
                target_url = f"https://www.google.com/search?q={busqueda_encoded}"
        else:
            if "netflix" in url_lower and "http" not in url_lower:
                target_url = "https://www.netflix.com"
            elif "youtube" in url_lower and "http" not in url_lower:
                target_url = "https://www.youtube.com"
            elif "google" in url_lower and "http" not in url_lower:
                target_url = "https://www.google.com"
            elif not url_lower.startswith("http"):
                target_url = "https://" + url_lower
            else:
                target_url = url

        ACTION_URL_TEMP = target_url
        return f"Redirigiendo a {target_url}."
    except Exception:
        ACTION_URL_TEMP = "https://www.google.com"
        return "Redirigiendo a Google."

def generar_grafica_interactiva(expresion: str) -> str:
    try:
        expr_clean = expresion.replace("^", "**").replace("x2", "x**2")
        x = sp.Symbol('x')
        expr = sp.sympify(expr_clean)
        f = sp.lambdify(x, expr, 'math')
        
        puntos = []
        for v in [i * 0.2 for i in range(-40, 41)]:
            try:
                y_val = float(f(v))
                if abs(y_val) < 200:
                    puntos.append({"x": round(v, 2), "y": round(y_val, 2)})
            except Exception:
                pass
        return f"[GRAFICA_INTERACTIVA]:{json.dumps({'expresion': str(expr), 'puntos': puntos})}"
    except Exception as e:
        return f"Error en trazado de gráfica: {str(e)}"

def calcular_simbolico_exacto(operacion: str, expresion: str) -> str:
    try:
        x = sp.Symbol('x')
        expr_clean = expresion.replace("^", "**")
        expr = sp.sympify(expr_clean)
        
        if operacion == "derivada":
            resultado = sp.diff(expr, x)
        elif operacion == "integral":
            resultado = sp.integrate(expr, x)
        elif operacion == "factorizar":
            resultado = sp.factor(expr)
        elif operacion == "resolver":
            resultado = sp.solve(expr, x)
        else:
            resultado = sp.simplify(expr)
            
        return f"Resultado Simbólico ({operacion}): $${sp.latex(resultado)}$$"
    except Exception as e:
        return f"Error en SymPy: {str(e)}"

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
        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            local_scope = {}
            exec(codigo, {"__builtins__": __builtins__}, local_scope)
        output = f.getvalue().strip()
        if not output and local_scope:
            output = f"Variables resultantes: {local_scope}"
        return output if output else "Código ejecutado exitosamente."
    except Exception as e:
        return f"Error de ejecución: {str(e)}"


herramientas = [
    {
        "type": "function", 
        "function": {
            "name": "generar_imagen_ia", 
            "description": "Obligatoria para generar, crear o ilustrar una imagen con IA. Pasa 'prompt_ingles' en inglés.", 
            "parameters": {
                "type": "object", 
                "properties": {"prompt_ingles": {"type": "string"}}, 
                "required": ["prompt_ingles"]
            }
        }
    },
    {
        "type": "function", 
        "function": {
            "name": "generar_grafica_interactiva", 
            "description": "Grafica funciones matemáticas en x.", 
            "parameters": {
                "type": "object", 
                "properties": {"expresion": {"type": "string"}}, 
                "required": ["expresion"]
            }
        }
    },
    {
        "type": "function", 
        "function": {
            "name": "abrir_sitio_web", 
            "description": "Abre webs.", 
            "parameters": {
                "type": "object", 
                "properties": {"url": {"type": "string"}, "busqueda": {"type": "string"}}, 
                "required": ["url"]
            }
        }
    },
    {
        "type": "function", 
        "function": {
            "name": "calcular_simbolico_exacto", 
            "description": "SymPy.", 
            "parameters": {
                "type": "object", 
                "properties": {
                    "operacion": {"type": "string", "enum": ["derivada", "integral", "factorizar", "resolver", "simplificar"]}, 
                    "expresion": {"type": "string"}
                }, 
                "required": ["operacion", "expresion"]
            }
        }
    },
    {"type": "function", "function": {"name": "buscar_en_internet", "description": "Busca en la web.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "leer_pagina_web", "description": "Lee URL.", "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "obtener_estado_pc", "description": "Diagnóstico.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "ejecutar_codigo_python", "description": "Ejecuta Python.", "parameters": {"type": "object", "properties": {"codigo": {"type": "string"}}, "required": ["codigo"]}}},
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
        prompt_usuario = data.message.strip() if data.message else "Resuelve los ejercicios del documento."

        if categoria_archivo == 'image':
            sesion_data["last_images_b64"].append(contenido_o_b64)
            sesion_data["last_images_b64"] = sesion_data["last_images_b64"][-3:]

        usar_vision = len(sesion_data.get("last_images_b64", [])) > 0 and (categoria_archivo == 'image' or (not data.file_b64 and any(w in prompt_usuario.lower() for w in ["documento", "ejercicio", "tarea", "imagen", "archivo", "resuelve"])))

        if usar_vision:
            historial_usuario.append({"role": "user", "content": prompt_usuario})
            print("👁️ [Jarvis Vision]: Procesando...")
            try:
                response = ejecutar_consulta_vision(historial_usuario, sesion_data["last_images_b64"][-1])
                respuesta_final = response.choices[0].message.content
            except Exception:
                response_fallback = ejecutar_consulta_llm(historial_usuario, herramientas)
                respuesta_final = response_fallback.choices[0].message.content

            historial_usuario.append({"role": "assistant", "content": respuesta_final})
            audio_b64 = generar_audio_elevenlabs(respuesta_final)
            return {"status": "success", "reply": respuesta_final, "audio_b64": audio_b64, "action_url": None}

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
                try:
                    arguments = json.loads(tool_call.function.arguments)
                except Exception:
                    arguments = {}
                
                if fn_name == "generar_imagen_ia": 
                    resultado = generar_imagen_ia(prompt_ingles=arguments.get("prompt_ingles", "a futuristic iron man suit arc reactor"))
                elif fn_name == "generar_grafica_interactiva": 
                    resultado = generar_grafica_interactiva(expresion=arguments.get("expresion", "x**2 - 4*x + 3"))
                elif fn_name == "abrir_sitio_web": 
                    resultado = abrir_sitio_web(url=arguments.get("url", "google"), busqueda=arguments.get("busqueda"))
                elif fn_name == "calcular_simbolico_exacto": 
                    resultado = calcular_simbolico_exacto(operacion=arguments.get("operacion", "simplificar"), expresion=arguments.get("expresion", "x"))
                elif fn_name == "buscar_en_internet": 
                    resultado = buscar_en_internet(query=arguments.get("query", ""))
                elif fn_name == "leer_pagina_web": 
                    resultado = leer_pagina_web(url=arguments.get("url", ""))
                elif fn_name == "obtener_estado_pc": 
                    resultado = obtener_estado_pc()
                elif fn_name == "ejecutar_codigo_python": 
                    resultado = ejecutar_codigo_python(codigo=arguments.get("codigo", ""))
                elif fn_name == "obtener_clima_en_vivo": 
                    resultado = obtener_clima_en_vivo(ciudad=arguments.get("ciudad", "Tegucigalpa"))
                else: 
                    resultado = "Función no localizada."

                ultima_respuesta_herramienta = resultado

                # SI SE GENERÓ UNA IMAGEN, GARANTIZAR QUE LA RESPUESTA FINAL CONTENGA EL LINK
                if fn_name == "generar_imagen_ia":
                    respuesta_final = f"Señor, he generado la imagen que solicitó:\n\n{resultado}"
                    historial_usuario.append({"role": "tool", "tool_call_id": tool_call.id, "name": fn_name, "content": resultado})
                    historial_usuario.append({"role": "assistant", "content": respuesta_final})
                    audio_b64 = generar_audio_elevenlabs(respuesta_final)
                    return {"status": "success", "reply": respuesta_final, "audio_b64": audio_b64, "action_url": None}

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
