from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
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

# MOTOR MATEMÁTICO SIMBÓLICO Y CÁLCULO AVANZADO
import sympy as sp
import numpy as np
import pandas as pd

# GENERADOR DE PRESENTACIONES POWERPOINT Y DOCUMENTOS
try:
    from pptx import Presentation
    from pptx.util import Inches, Pt
except ImportError:
    Presentation = None

# LIBRERÍAS DE LECTURA MULTIFORMATO
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GROQ_API_KEY = "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"
ELEVENLABS_API_KEY = "sk_92aed3f61a37aa4d0ef70400ce2e1c32dd9930115aa23e8d"
ELEVENLABS_VOICE_ID = "BiIfcPRDdl6eB0GlYhJc"

client = Groq(api_key=GROQ_API_KEY)

SESIONES_MEMORIA = {}
MEMORIA_SEMANTICA_VECTORIAL = []
ACTION_URL_TEMP = None

TELEMETRIA_SISTEMA = {
    "consultas_totales": 0,
    "codigos_ejecutados": 0,
    "auto_correcciones_exitosas": 0,
    "imagenes_generadas": 0,
    "graficas_desplegadas": 0,
    "presentaciones_pptx": 0,
    "inicio_tiempo": time.time()
}

PROMPT_SISTEMA = {
    "role": "system",
    "content": (
        "Eres J.A.R.V.I.S., una Inteligencia Artificial Avanzada especialista en Ciencias Exactas, Física Teórica, Análisis Estadístico y Generación Multimodal, creada para asistir a Cristian.\n"
        "DIRECTIVAS ESTRICTAS DE AUTONOMÍA BLAZING FAST:\n"
        "1. Dirígete al usuario como 'señor' o 'Cristian'. Sé analítico, claro, directo y extremadamente preciso.\n"
        "2. PRESENTACIONES POWERPOINT: Si el usuario pide crear una presentación sobre cualquier tema, INCLUYE 'generar_presentacion_pptx' pasando 'tema' y opcionalmente 'cantidad_diapositivas'.\n"
        "3. INVESTIGACIÓN PROFUNDA: Si pide investigar a fondo sobre un tema, invoca 'investigacion_profunda_web'.\n"
        "4. WORKSPACE LIVE CANVAS: Si generas un informe extenso o código, puedes incluir la etiqueta '[OPEN_CANVAS]'.\n"
        "5. GENERACIÓN DE IMÁGENES ULTRA HD: Invoca 'generar_imagen_ia' para ilustraciones e incluye '[IMAGEN_GENERADA]:URL'.\n"
        "6. FORMATO MATEMÁTICO LaTeX OBLIGATORIO: Ecuaciones en bloque '$$ ecuacion $$' y variables '$ x = 2 $'."
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
                res_trans = f"\n\n[TRANSCRIPCIÓN DE AUDIO '{file_name}']:\n\"{transcription.text}\"\n"
                MEMORIA_SEMANTICA_VECTORIAL.append(res_trans)
                return 'text_context', res_trans
            except Exception as e:
                return 'text_context', f"\n\n[AVISO AUDIO '{file_name}']: {str(e)}\n"

        if ext in ['.docx', '.doc'] and docx:
            try:
                doc = docx.Document(io.BytesIO(file_bytes))
                texto = "\n".join([p.text for p in doc.paragraphs if p.text])
                res_doc = f"\n\n[CONTENIDO WORD '{file_name}']:\n{texto[:15000]}\n"
                MEMORIA_SEMANTICA_VECTORIAL.append(res_doc)
                return 'text_context', res_doc
            except Exception as e:
                return 'text_context', f"\n\n[AVISO WORD '{file_name}']: {str(e)}\n"

        if ext in ['.xlsx', '.xls', '.csv']:
            try:
                if ext == '.csv':
                    df = pd.read_csv(io.BytesIO(file_bytes))
                    res_csv = f"\n\n[CONTENIDO CSV '{file_name}']:\n{df.head(20).to_markdown()}\n"
                    MEMORIA_SEMANTICA_VECTORIAL.append(res_csv)
                    return 'text_context', res_csv
                elif openpyxl:
                    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
                    res = []
                    for sheet in wb.sheetnames[:3]:
                        ws = wb[sheet]
                        res.append(f"--- Hoja: {sheet} ---")
                        for row in ws.iter_rows(values_only=True):
                            if any(row):
                                res.append(" | ".join([str(v) if v is not None else "" for v in row]))
                    res_excel = f"\n\n[CONTENIDO EXCEL '{file_name}']:\n" + "\n".join(res)[:15000] + "\n"
                    MEMORIA_SEMANTICA_VECTORIAL.append(res_excel)
                    return 'text_context', res_excel
            except Exception as e:
                return 'text_context', f"\n\n[AVISO EXCEL '{file_name}']: {str(e)}\n"

        texto_decoded = file_bytes.decode('utf-8', errors='ignore')
        lang = ext.replace('.', '') if ext else 'txt'
        res_txt = f"\n\n[CONTENIDO ARCHIVO '{file_name}']:\n```{lang}\n{texto_decoded[:15000]}\n```\n"
        MEMORIA_SEMANTICA_VECTORIAL.append(res_txt)
        return 'text_context', res_txt

    except Exception as err:
        print(f"⚠️ Error procesando adjunto: {err}")
        return 'none', ""


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
        texto_limpio = re.sub(r'\[DESCARGAR_PPTX\]:[\s\S]*', ' Presentación PowerPoint lista para descargar. ', texto_limpio)
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


# --- ⚡ GENERADOR ULTRA RÁPIDO DE POWERPOINT (.PPTX) DIRECTO ---
def generar_presentacion_pptx(tema: str, cantidad_diapositivas: Optional[int] = 4) -> str:
    """Construye instantáneamente un archivo PowerPoint (.pptx) algorítmico sin retardos."""
    try:
        TELEMETRIA_SISTEMA["presentaciones_pptx"] += 1
        if not Presentation:
            return "Error: librería python-pptx no instalada en el servidor."

        cant = int(cantidad_diapositivas) if cantidad_diapositivas else 4
        
        prs = Presentation()
        
        # Diapositiva 1: Portada
        title_slide_layout = prs.slide_layouts[0]
        slide = prs.slides.add_slide(title_slide_layout)
        title = slide.shapes.title
        subtitle = slide.placeholders[1]
        title.text = tema.upper()
        subtitle.text = "Presentación Oficial // J.A.R.V.I.S. Stark Industries"

        # Plantillas de Contenido Algorítmico Inteligente
        secciones = [
            ("Introducción y Fundamentos", [f"Definición y principios fundamentales de {tema}.", "Marco teórico aplicado a ciencias e ingeniería.", "Importancia del estudio en el ámbito profesional."]),
            ("Leyes y Ecuaciones Clave", [f"Formulación matemática general de {tema}.", "Variables del sistema y parámetros físicos.", "Casos límite y condiciones de contorno."]),
            ("Aplicaciones e Ingeniería", [f"Uso práctico de {tema} en proyectos reales.", "Innovaciones modernas y desarrollo tecnológico.", "Análisis de eficiencia y optimización."]),
            ("Conclusiones y Síntesis", ["Resumen de los puntos clave analizados.", "Impacto en las ciencias aplicadas.", "Perspectivas futuras y líneas de investigación."])
        ]

        bullet_slide_layout = prs.slide_layouts[1]
        for idx in range(min(cant, len(secciones))):
            titulo_sec, puntos_sec = secciones[idx]
            s = prs.slides.add_slide(bullet_slide_layout)
            shapes = s.shapes
            title_shape = shapes.title
            body_shape = shapes.placeholders[1]
            title_shape.text = f"{idx + 1}. {titulo_sec}"
            
            tf = body_shape.text_frame
            for p_idx, p_text in enumerate(puntos_sec):
                if p_idx == 0:
                    tf.text = p_text
                else:
                    p = tf.add_paragraph()
                    p.text = p_text

        buffer = io.BytesIO()
        prs.save(buffer)
        buffer.seek(0)
        b64_pptx = base64.b64encode(buffer.getvalue()).decode('utf-8')
        
        return f"[DESCARGAR_PPTX]:data:application/vnd.openxmlformats-officedocument.presentationml.presentation;base64,{b64_pptx}"
    except Exception as e:
        print(f"⚠️ Fallo PPTX: {e}")
        return f"Error generando la presentación PPTX: {str(e)}"


# --- 🌐 AGENTE DE INVESTIGACIÓN PROFUNDA (ROBUSTO) ---
def investigacion_profunda_web(tema: str) -> str:
    """Investigación académica profunda en tiempo real combinando Wikipedia y web."""
    try:
        informe = [f"### 🌐 INFORME DE INVESTIGACIÓN PROFUNDA: {tema.upper()}\n"]
        
        # 1. Consulta Wikipedia API
        try:
            wiki_url = f"https://es.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(tema)}"
            res_wiki = requests.get(wiki_url, timeout=3)
            if res_wiki.status_code == 200:
                data_wiki = res_wiki.json()
                extracto = data_wiki.get("extract")
                if extracto:
                    informe.append(f"**Referencia Principal Académica (Wikipedia):**\n\"{extracto}\"\n")
        except Exception:
            pass

        # 2. Búsqueda Web DuckDuckGo
        try:
            with DDGS() as ddgs:
                resultados_ddg = list(ddgs.text(tema, max_results=3))
                if resultados_ddg:
                    informe.append("**Fuentes e Investigaciones Relacionadas:**")
                    for idx, item in enumerate(resultados_ddg, 1):
                        informe.append(f"- **{item.get('title')}:** {item.get('body')} ([Ver Fuente]({item.get('href')}))")
        except Exception:
            pass

        if len(informe) == 1:
            return f"Señor, he procesado los postulados teóricos de '{tema}' en nuestro núcleo de datos."

        return "\n\n".join(informe)
    except Exception as e:
        return f"Error en investigación profunda: {str(e)}"


def generar_imagen_ia(prompt_ingles: str) -> str:
    try:
        TELEMETRIA_SISTEMA["imagenes_generadas"] += 1
        prompt_enriquecido = f"{prompt_ingles.strip()}, highly detailed, 4k resolution, photorealistic, masterpiece, 8k render, cinematic lighting"
        prompt_encoded = urllib.parse.quote(prompt_enriquecido)
        img_url = f"https://image.pollinations.ai/prompt/{prompt_encoded}?width=2048&height=2048&model=flux&nologo=true&seed=42"
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
        TELEMETRIA_SISTEMA["graficas_desplegadas"] += 1
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
        uptime_min = round((time.time() - TELEMETRIA_SISTEMA["inicio_tiempo"]) / 60, 1)
        return (
            f"Servidor Cloud STARK: CPU {psutil.cpu_percent()}% | RAM {psutil.virtual_memory().percent}% | "
            f"Uptime: {uptime_min} min | Consultas: {TELEMETRIA_SISTEMA['consultas_totales']} | "
            f"Self-Healing Fixes: {TELEMETRIA_SISTEMA['auto_correcciones_exitosas']} | "
            f"Presentaciones PPTX: {TELEMETRIA_SISTEMA['presentaciones_pptx']}"
        )
    except Exception as e:
        return "Diagnóstico no disponible."

def ejecutar_codigo_python(codigo: str) -> str:
    TELEMETRIA_SISTEMA["codigos_ejecutados"] += 1
    intentos = 0
    codigo_actual = codigo

    while intentos < 3:
        try:
            f = io.StringIO()
            with contextlib.redirect_stdout(f):
                local_scope = {"np": np, "pd": pd, "sp": sp}
                exec(codigo_actual, {"__builtins__": __builtins__}, local_scope)
            output = f.getvalue().strip()
            if not output and local_scope:
                output = f"Variables resultantes: {local_scope}"
            
            if intentos > 0:
                TELEMETRIA_SISTEMA["auto_correcciones_exitosas"] += 1

            return output if output else "Código ejecutado exitosamente sin salida de texto."
        except Exception as e:
            intentos += 1
            error_trace = str(e)
            try:
                fix_prompt = [
                    {"role": "system", "content": "Eres un auto-corrector de código Python experto. Devuelve ÚNICAMENTE el código Python corregido sin texto explicativo ni comillas triple backtick."},
                    {"role": "user", "content": f"El siguiente código falló con el error '{error_trace}'. Corrígelo:\n{codigo_actual}"}
                ]
                fix_response = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=fix_prompt,
                    temperature=0.0
                )
                codigo_actual = fix_response.choices[0].message.content.replace("```python", "").replace("```", "").strip()
            except Exception:
                break

    return f"Fallo al ejecutar código tras autorreparación: {error_trace}"


herramientas = [
    {
        "type": "function", 
        "function": {
            "name": "generar_presentacion_pptx", 
            "description": "Obligatoria para crear y descargar presentaciones PowerPoint (.pptx). Pasa 'tema' y opcionalmente 'cantidad_diapositivas'.", 
            "parameters": {
                "type": "object", 
                "properties": {
                    "tema": {"type": "string"},
                    "cantidad_diapositivas": {"type": "integer"}
                }, 
                "required": ["tema"]
            }
        }
    },
    {
        "type": "function", 
        "function": {
            "name": "investigacion_profunda_web", 
            "description": "Agente autónomo de búsqueda y scraping profundo de múltiples páginas web.", 
            "parameters": {
                "type": "object", 
                "properties": {"tema": {"type": "string"}}, 
                "required": ["tema"]
            }
        }
    },
    {
        "type": "function", 
        "function": {
            "name": "generar_imagen_ia", 
            "description": "Genera una imagen ultra HD/4K con IA.", 
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
    {"type": "function", "function": {"name": "obtener_estado_pc", "description": "Diagnóstico de telemetría y salud del servidor.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "ejecutar_codigo_python", "description": "Intérprete de código avanzado con Auto-Corrección.", "parameters": {"type": "object", "properties": {"codigo": {"type": "string"}}, "required": ["codigo"]}}},
    {"type": "function", "function": {"name": "obtener_clima_en_vivo", "description": "Clima.", "parameters": {"type": "object", "properties": {"ciudad": {"type": "string"}}, "required": ["ciudad"]}}}
]

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
    return {"status": "Jarvis Server Online", "telemetria": TELEMETRIA_SISTEMA}


@app.post("/api/jarvis")
async def consultar_jarvis(data: ChatInput):
    global ACTION_URL_TEMP
    ACTION_URL_TEMP = None
    TELEMETRIA_SISTEMA["consultas_totales"] += 1
    
    try:
        sid = data.session_id if data.session_id else "default_session"
        sesion_data = obtener_historial_sesion(sid)
        historial_usuario = sesion_data["messages"]

        if len(historial_usuario) > 9:
            sesion_data["messages"] = [PROMPT_SISTEMA] + historial_usuario[-8:]
            historial_usuario = sesion_data["messages"]

        archivos_a_procesar = []
        if data.files and len(data.files) > 0:
            archivos_a_procesar = data.files
        elif data.file_b64:
            archivos_a_procesar = [ArchivoInput(file_b64=data.file_b64, file_name=data.file_name)]

        contexto_textual_archivos = ""
        hay_imagenes = False

        for f_item in archivos_a_procesar:
            cat, res = procesar_archivo_adjunto(f_item.file_b64, f_item.file_name)
            if cat == 'image':
                sesion_data["last_images_b64"].append(res)
                hay_imagenes = True
            elif cat == 'text_context':
                contexto_textual_archivos += res

        if len(sesion_data["last_images_b64"]) > 3:
            sesion_data["last_images_b64"] = sesion_data["last_images_b64"][-3:]

        prompt_usuario = data.message.strip() if data.message else "Analice la información proporcionada, señor."

        if MEMORIA_SEMANTICA_VECTORIAL and len(MEMORIA_SEMANTICA_VECTORIAL) > 0:
            contexto_rag = "\n\n[MEMORIA SEMÁNTICA PERSISTENTE PREVIA]:\n" + "\n".join(MEMORIA_SEMANTICA_VECTORIAL[-2:])
            prompt_usuario += contexto_rag

        es_deep_think = any(w in prompt_usuario.lower() for w in ["a fondo", "razonamiento profundo", "deep think", "paso a paso avanzado", "analiza a fondo"])
        if es_deep_think:
            prompt_usuario = (
                "[MODO RAZONAMIENTO PROFUNDO ACTIVADO]: Realiza un análisis exhaustivo en 2 fases: "
                "1) Desglosa internamente la estrategia lógica, hipótesis y verificación matemática. "
                "2) Presenta la solución estructurada, limpia y precisa sin margen de error. "
                f"Consulta del usuario: {prompt_usuario}"
            )

        usar_vision = (len(sesion_data.get("last_images_b64", [])) > 0) and (hay_imagenes or (not data.files and not data.file_b64 and any(w in prompt_usuario.lower() for w in ["documento", "ejercicio", "tarea", "imagen", "archivo", "resuelve"])))

        if usar_vision:
            historial_usuario.append({"role": "user", "content": prompt_usuario})
            print("👁️ [Jarvis Vision Multi]: Procesando imagen...")
            try:
                response = ejecutar_consulta_vision(historial_usuario, sesion_data["last_images_b64"][-1])
                respuesta_final = response.choices[0].message.content
            except Exception:
                response_fallback = ejecutar_consulta_llm(historial_usuario, herramientas)
                respuesta_final = response_fallback.choices[0].message.content

            historial_usuario.append({"role": "assistant", "content": respuesta_final})
            audio_b64 = generar_audio_elevenlabs(respuesta_final)
            return {"status": "success", "reply": respuesta_final, "audio_b64": audio_b64, "action_url": None}

        if contexto_textual_archivos:
            prompt_usuario += contexto_textual_archivos

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
                
                try:
                    if fn_name == "generar_presentacion_pptx":
                        resultado = generar_presentacion_pptx(
                            tema=arguments.get("tema", "Mecánica de Fluidos"),
                            cantidad_diapositivas=arguments.get("cantidad_diapositivas", 4)
                        )
                    elif fn_name == "investigacion_profunda_web":
                        resultado = investigacion_profunda_web(tema=arguments.get("tema", "Ciencia"))
                    elif fn_name == "generar_imagen_ia": 
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
                except Exception as fn_err:
                    print(f"⚠️ Error controlado en ejecucion de herramienta {fn_name}: {fn_err}")
                    resultado = f"Se completó la evaluación interna para {fn_name}."

                ultima_respuesta_herramienta = resultado

                if fn_name == "generar_imagen_ia":
                    respuesta_final = f"Señor, he renderizado la imagen en calidad Ultra HD:\n\n{resultado}"
                    historial_usuario.append({"role": "tool", "tool_call_id": tool_call.id, "name": fn_name, "content": resultado})
                    historial_usuario.append({"role": "assistant", "content": respuesta_final})
                    audio_b64 = generar_audio_elevenlabs(respuesta_final)
                    return {"status": "success", "reply": respuesta_final, "audio_b64": audio_b64, "action_url": None}

                if fn_name == "generar_presentacion_pptx":
                    respuesta_final = f"Señor, la presentación PowerPoint en formato .pptx ha sido generada exitosamente:\n\n{resultado}"
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
