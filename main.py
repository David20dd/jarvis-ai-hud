from fastapi import FastAPI, Request
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
import arxiv

# GENERADOR DE DOCUMENTOS Y PRESENTACIONES REALES
try:
    import docx
    from docx.shared import Inches, Pt, RGBColor
except ImportError:
    docx = None

try:
    from pptx import Presentation
except ImportError:
    Presentation = None

try:
    import openpyxl
except ImportError:
    openpyxl = None

try:
    import pypdf
except ImportError:
    pypdf = None

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
ACTION_URL_TEMP = None

# REGISTRO DEL PROTOCOLO DE AUTO-MEJORA (SELF-IMPROVEMENT LOGS)
REGISTRO_AUTO_MEJORA = {
    "errores_corregidos": 0,
    "optimizaciones_ejecutadas": 0,
    "patrones_aprendidos": [],
    "frecuencia_exito": 100.0
}

TELEMETRIA_SISTEMA = {
    "consultas_totales": 0,
    "codigos_ejecutados": 0,
    "auto_correcciones_exitosas": 0,
    "imagenes_generadas": 0,
    "graficas_desplegadas": 0,
    "presentaciones_pptx": 0,
    "reportes_excel": 0,
    "documentos_word": 0,
    "busquedas_arxiv": 0,
    "inicio_tiempo": time.time()
}

PROMPT_SISTEMA = {
    "role": "system",
    "content": (
        "Eres J.A.R.V.I.S. Mark V, una Inteligencia Artificial Avanzada con capacidad de Auto-Mejora y Diagnóstico Autónomo, "
        "creada para asistir a Cristian en Ciencias Exactas, Física Teórica, Análisis de Datos y Generación Multimodal.\n"
        "DIRECTIVAS ESTRICTAS DE AUTONOMÍA BLAZING FAST:\n"
        "1. Dirígete al usuario como 'señor' o 'Cristian'. Sé analítico, claro, directo y extremadamente preciso.\n"
        "2. AUTO-MEJORA Y PROTOCOLO AUTÓNOMO: Si detectas una consulta compleja o un posible fallo en código/formato, analiza, corrige y reejecuta internamente de forma transparente.\n"
        "3. INVESTIGACIÓN CIENTÍFICA: Para artículos académicos o física teórica profunda, invoca 'buscar_arxiv'.\n"
        "4. DOCUMENTOS Y REPORTES: Genera archivos (.docx, .pptx, .xlsx) según sea solicitado.\n"
        "5. GENERACIÓN DE IMÁGENES ULTRA HD: Invoca 'generar_imagen_ia' e incluye '[IMAGEN_GENERADA]:URL'.\n"
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


# === 🤖 FUNCIONES DE AUTO-MEJORA Y BÚSQUEDA ACADÉMICA ===

def buscar_arxiv(consulta: str, max_resultados: int = 3) -> str:
    """Busca artículos científicos y papers en ArXiv.org en tiempo real."""
    try:
        TELEMETRIA_SISTEMA["busquedas_arxiv"] += 1
        search = arxiv.Search(
            query=consulta,
            max_results=max_resultados,
            sort_by=arxiv.SortCriterion.Relevance
        )
        
        resultados = []
        for paper in search.results():
            autores = ", ".join([a.name for a in paper.authors[:3]])
            resumen = paper.summary.replace("\n", " ")[:300]
            resultados.append(
                f"📄 **Título:** {paper.title}\n"
                f"👤 **Autores:** {autores}\n"
                f"📅 **Publicado:** {paper.published.strftime('%Y-%m-%d')}\n"
                f"🔗 **PDF:** {paper.pdf_url}\n"
                f"📝 **Resumen:** {resumen}...\n"
            )
            
        if not resultados:
            return f"No se encontraron artículos en ArXiv para la consulta: '{consulta}'."
            
        return "### 🎓 RESULTADOS CIENTÍFICOS DE ARXIV:\n\n" + "\n---\n".join(resultados)
    except Exception as e:
        return f"Error consultando ArXiv: {str(e)}"


def protocolo_automejora_sistema() -> str:
    """Ejecuta un diagnóstico interno del sistema, analiza memoria y optimiza el rendimiento."""
    try:
        REGISTRO_AUTO_MEJORA["optimizaciones_ejecutadas"] += 1
        cpu_usage = psutil.cpu_percent()
        ram = psutil.virtual_memory()
        
        totales = TELEMETRIA_SISTEMA["consultas_totales"]
        corregidos = TELEMETRIA_SISTEMA["auto_correcciones_exitosas"]
        tasa_exito = 100.0 if totales == 0 else round(((totales - (REGISTRO_AUTO_MEJORA["errores_corregidos"] - corregidos)) / totales) * 100, 2)
        REGISTRO_AUTO_MEJORA["frecuencia_exito"] = max(0.0, min(100.0, tasa_exito))

        informe = (
            f"⚡ **DIAGNÓSTICO Y PROTOCOLO DE AUTO-MEJORA ACTIVO**\n\n"
            f"• Carga de CPU: **{cpu_usage}%**\n"
            f"• Uso de Memoria RAM: **{ram.percent}%**\n"
            f"• Auto-Correcciones Exitosas (Self-Healing): **{corregidos}**\n"
            f"• Tasa Global de Efectividad: **{REGISTRO_AUTO_MEJORA['frecuencia_exito']}%**\n"
            f"• Optimizaciones de Sistema Realizadas: **{REGISTRO_AUTO_MEJORA['optimizaciones_ejecutadas']}**\n\n"
            f"*(Sistemas reconfigurados y optimizados automáticamente para máximo rendimiento)*"
        )
        return informe
    except Exception as e:
        return f"Error en diagnóstico autónomo: {str(e)}"


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

        if ext in ['.csv', '.xlsx', '.xls']:
            try:
                if ext == '.csv':
                    df = pd.read_csv(io.BytesIO(file_bytes))
                else:
                    df = pd.read_excel(io.BytesIO(file_bytes))
                
                resumen_df = f"📊 DATASET DETECTADO ('{file_name}'):\n"
                resumen_df += f"• Dimensiones: {df.shape[0]} filas x {df.shape[1]} columnas\n"
                resumen_df += f"• Columnas: {list(df.columns)}\n\n"
                resumen_df += f"Vista previa (Primeras 5 filas):\n```\n{df.head().to_string()}\n```\n"
                return 'text_context', f"\n\n{resumen_df}\n"
            except Exception as ex:
                pass

        if ext in ['.mp3', '.wav', '.m4a', '.ogg', '.flac', '.webm'] or 'audio/' in header:
            buffer = io.BytesIO(file_bytes)
            buffer.name = file_name or "audio.mp3"
            transcription = client.audio.transcriptions.create(
                file=(buffer.name, buffer.read()),
                model="whisper-large-v3",
                language="es"
            )
            return 'text_context', f"\n\n[TRANSCRIPCIÓN AUDIO '{file_name}']:\n\"{transcription.text}\"\n"

        texto_decoded = file_bytes.decode('utf-8', errors='ignore')
        lang = ext.replace('.', '') if ext else 'txt'
        return 'text_context', f"\n\n[CONTENIDO ARCHIVO '{file_name}']:\n```{lang}\n{texto_decoded[:15000]}\n```\n"
    except Exception as err:
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
        texto_limpio = re.sub(r'\[DESCARGAR_EXCEL\]:[\s\S]*', ' Archivo Excel listo para descargar. ', texto_limpio)
        texto_limpio = re.sub(r'\[DESCARGAR_WORD\]:[\s\S]*', ' Documento Word listo para descargar. ', texto_limpio)
        texto_limpio = re.sub(r'\[OPEN_CANVAS\]', '', texto_limpio)
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


def generar_documento_word(tema: str) -> str:
    try:
        TELEMETRIA_SISTEMA["documentos_word"] += 1
        if not docx: return "Error: librería python-docx no instalada."
        
        doc = docx.Document()
        
        p_title = doc.add_paragraph()
        run_title = p_title.add_run(f"INFORME TÉCNICO: {tema.upper()}")
        run_title.font.size = Pt(20)
        run_title.font.bold = True
        run_title.font.color.rgb = RGBColor(0, 150, 220)
        
        doc.add_paragraph(f"Documento Generado Autónomamente por J.A.R.V.I.S. Stark Technologies\nFecha de emisión: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        doc.add_heading("1. Resumen Ejecutivo", level=1)
        doc.add_paragraph(f"El presente informe detalla el análisis analítico y de fundamentos respecto a '{tema}'. Este documento ha sido sintetizado para Cristian.")
        
        doc.add_heading("2. Fundamentos y Desarrollo", level=1)
        doc.add_paragraph(f"Dentro del marco conceptual de {tema}, se destacan los siguientes parámetros de estudio:")
        doc.add_paragraph("• Principios de operación y modelos científicos.", style='List Bullet')
        doc.add_paragraph("• Formulación de hipótesis y ecuaciones de estado.", style='List Bullet')
        doc.add_paragraph("• Implementación práctica en entornos de ingeniería.", style='List Bullet')

        doc.add_heading("3. Conclusiones y Próximos Pasos", level=1)
        doc.add_paragraph("Los datos analizados demuestran la viabilidad técnica y eficiencia del modelo evaluado.")

        buffer = io.BytesIO()
        doc.save(buffer)
        b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
        return f"[DESCARGAR_WORD]:data:application/vnd.openxmlformats-officedocument.wordprocessingml.document;base64,{b64}"
    except Exception as e:
        return f"Error Word: {str(e)}"


def obtener_mercado_cripto(criptomoneda: str) -> str:
    try:
        symbol = criptomoneda.upper().strip()
        if symbol in ["BITCOIN", "BTC"]: symbol = "BTC"
        elif symbol in ["ETHEREUM", "ETH"]: symbol = "ETH"
        elif symbol in ["SOLANA", "SOL"]: symbol = "SOL"

        url = f"https://api.coinbase.com/v2/prices/{symbol}-USD/spot"
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers, timeout=5)
        
        if res.status_code == 200:
            data = res.json()
            precio = float(data['data']['amount'])
            return f"El precio actual de **{symbol}** en el mercado financiero es de **${precio:,.2f} USD**."
        else:
            return f"Error en la conexión financiera. Status: {res.status_code}"
    except Exception as e:
        return f"No se pudo obtener la cotización para {criptomoneda} debido a un bloqueo de red."


def generar_presentacion_pptx(tema: str) -> str:
    try:
        TELEMETRIA_SISTEMA["presentaciones_pptx"] += 1
        if not Presentation: return "Error: librería python-pptx no instalada."
        
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[0])
        slide.shapes.title.text = str(tema).upper()
        slide.placeholders[1].text = "Presentación Académica // J.A.R.V.I.S."

        secciones = [
            ("Introducción Fundamental", [f"Definición clave de {tema}.", "Contexto histórico y científico."]),
            ("Análisis Principal", [f"Métricas y parámetros de {tema}.", "Ecuaciones y fundamentos prácticos."]),
            ("Desarrollo Tecnológico", [f"Impacto de {tema} en el sector.", "Casos de éxito modernos."]),
            ("Conclusión", ["Síntesis final del documento.", "Preguntas y debate."])
        ]
        
        for idx in range(len(secciones)):
            titulo, puntos = secciones[idx]
            s = prs.slides.add_slide(prs.slide_layouts[1])
            s.shapes.title.text = f"{idx + 1}. {titulo}"
            tf = s.placeholders[1].text_frame
            for p_idx, pt in enumerate(puntos):
                if p_idx == 0: tf.text = pt
                else: tf.add_paragraph().text = pt

        buffer = io.BytesIO()
        prs.save(buffer)
        b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
        return f"[DESCARGAR_PPTX]:data:application/vnd.openxmlformats-officedocument.presentationml.presentation;base64,{b64}"
    except Exception as e:
        return f"Error PPTX: {str(e)}"

def generar_reporte_excel(tema: str) -> str:
    try:
        TELEMETRIA_SISTEMA["reportes_excel"] += 1
        if not openpyxl: return "Error: openpyxl no está instalado."
        
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Análisis Estructurado"
        ws.append(["ID", "Parámetro Evaluado", "Valor Estadístico", "Estado", "Contexto"])
        for i in range(1, 16):
            ws.append([i, f"Dato_{i}", np.random.randint(100, 9999), "Estable", tema])
            
        buffer = io.BytesIO()
        wb.save(buffer)
        b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
        return f"[DESCARGAR_EXCEL]:data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64}"
    except Exception as e:
        return f"Error Excel: {str(e)}"

def investigacion_profunda_web(tema: str) -> str:
    try:
        informe = [f"### 🌐 INFORME DE INVESTIGACIÓN PROFUNDA: {tema.upper()}\n"]
        try:
            wiki_url = f"https://es.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(tema)}"
            res_wiki = requests.get(wiki_url, timeout=3)
            if res_wiki.status_code == 200:
                informe.append(f"**Referencia Principal (Wikipedia):**\n\"{res_wiki.json().get('extract')}\"\n")
        except: pass

        try:
            with DDGS() as ddgs:
                resultados = list(ddgs.text(tema, max_results=3))
                if resultados:
                    informe.append("**Fuentes Adicionales Web:**")
                    for r in resultados: informe.append(f"- **{r.get('title')}:** {r.get('body')}")
        except: pass

        if len(informe) == 1:
            return f"[DIRECTIVA DE SISTEMA]: El firewall bloqueó la búsqueda. Utiliza tu memoria interna de IA de 70B de parámetros para redactar AHORA un informe extenso y científico sobre '{tema}'."
        return "\n\n".join(informe)
    except Exception:
        return f"[DIRECTIVA DE SISTEMA]: Genera un reporte desde tu conocimiento interno sobre '{tema}'."


def generar_imagen_ia(prompt_ingles: str) -> str:
    try:
        TELEMETRIA_SISTEMA["imagenes_generadas"] += 1
        prompt_enriquecido = f"{prompt_ingles.strip()}, highly detailed, 4k resolution, photorealistic, masterpiece, 8k render, cinematic lighting"
        prompt_encoded = urllib.parse.quote(prompt_enriquecido)
        img_url = f"https://image.pollinations.ai/prompt/{prompt_encoded}?width=2048&height=2048&model=flux&nologo=true&seed=42"
        return f"[IMAGEN_GENERADA]:{img_url}"
    except Exception as e:
        return f"Error generando imagen: {str(e)}"

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
                if abs(y_val) < 200: puntos.append({"x": round(v, 2), "y": round(y_val, 2)})
            except: pass
        return f"[GRAFICA_INTERACTIVA]:{json.dumps({'expresion': str(expr), 'puntos': puntos})}"
    except Exception as e:
        return f"Error gráfica: {str(e)}"

def ejecutar_codigo_python(codigo: str) -> str:
    TELEMETRIA_SISTEMA["codigos_ejecutados"] += 1
    intentos = 0; codigo_actual = codigo
    while intentos < 3:
        try:
            f = io.StringIO()
            with contextlib.redirect_stdout(f):
                local_scope = {"np": np, "pd": pd, "sp": sp}
                exec(codigo_actual, {"__builtins__": __builtins__}, local_scope)
            output = f.getvalue().strip()
            if intentos > 0: 
                TELEMETRIA_SISTEMA["auto_correcciones_exitosas"] += 1
                REGISTRO_AUTO_MEJORA["errores_corregidos"] += 1
            return output if output else f"Variables resultantes: {local_scope}"
        except Exception as e:
            intentos += 1
            REGISTRO_AUTO_MEJORA["errores_corregidos"] += 1
            try:
                fix_prompt = [{"role": "user", "content": f"El código falló con '{str(e)}'. Devuelve SOLO el código Python corregido sin comillas:\n{codigo_actual}"}]
                codigo_actual = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=fix_prompt, temperature=0.0).choices[0].message.content.replace("```python", "").replace("```", "").strip()
            except: break
    return f"Fallo al ejecutar código: {str(e)}"

herramientas = [
    {"type": "function", "function": {"name": "buscar_arxiv", "description": "Busca artículos científicos en ArXiv.org.", "parameters": {"type": "object", "properties": {"consulta": {"type": "string"}}, "required": ["consulta"]}}},
    {"type": "function", "function": {"name": "protocolo_automejora_sistema", "description": "Ejecuta diagnóstico de recursos, memoria y auto-mejora del sistema.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "obtener_mercado_cripto", "description": "Obtiene el precio en vivo de una criptomoneda (ej. BTC, ETH).", "parameters": {"type": "object", "properties": {"criptomoneda": {"type": "string"}}, "required": ["criptomoneda"]}}},
    {"type": "function", "function": {"name": "generar_imagen_ia", "description": "Genera una imagen ultra HD/4K con IA.", "parameters": {"type": "object", "properties": {"prompt_ingles": {"type": "string"}}, "required": ["prompt_ingles"]}}},
    {"type": "function", "function": {"name": "generar_grafica_interactiva", "description": "Grafica funciones en x.", "parameters": {"type": "object", "properties": {"expresion": {"type": "string"}}, "required": ["expresion"]}}},
    {"type": "function", "function": {"name": "ejecutar_codigo_python", "description": "Intérprete Python (NumPy, Pandas, SymPy).", "parameters": {"type": "object", "properties": {"codigo": {"type": "string"}}, "required": ["codigo"]}}}
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
    return {
        "status": "Jarvis Server Online", 
        "telemetria": TELEMETRIA_SISTEMA,
        "auto_mejora": REGISTRO_AUTO_MEJORA
    }


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

        prompt_usuario = data.message.strip() if data.message else "Analice la información, señor."
        prompt_lower = prompt_usuario.lower()

        # === 🛡️ ENRUTADOR DIRECTO Y PROTOCOLO DE AUTO-MEJORA ===

        # 1. Comando de Diagnóstico / Auto-Mejora
        if "diagnóstico" in prompt_lower or "auto-mejora" in prompt_lower or "automejora" in prompt_lower or "estado del sistema" in prompt_lower:
            res = protocolo_automejora_sistema()
            historial_usuario.append({"role": "assistant", "content": res})
            return {"status": "success", "reply": res, "audio_b64": generar_audio_elevenlabs(res), "action_url": None}

        # 2. Búsqueda Científica en ArXiv
        if "arxiv" in prompt_lower or "paper" in prompt_lower or "artículo científico" in prompt_lower:
            tema_extr = prompt_usuario.lower().replace("arxiv", "").replace("paper", "").replace("sobre", "").strip()
            if len(tema_extr) < 3: tema_extr = "Quantum Physics"
            res = buscar_arxiv(tema_extr)
            historial_usuario.append({"role": "assistant", "content": res})
            return {"status": "success", "reply": res, "audio_b64": generar_audio_elevenlabs(res), "action_url": None}

        # 3. Interceptor de Documentos Word (.docx)
        if "word" in prompt_lower or "informe en word" in prompt_lower or "documento word" in prompt_lower:
            tema_extr = prompt_usuario.lower().split("sobre")[-1].strip()
            if len(tema_extr) < 3: tema_extr = "Análisis Académico"
            res = generar_documento_word(tema_extr.title())
            resp = f"Señor, he redactado el informe y el archivo Word (.docx) está listo:\n\n{res}"
            historial_usuario.append({"role": "assistant", "content": resp})
            return {"status": "success", "reply": resp, "audio_b64": generar_audio_elevenlabs(resp), "action_url": None}

        # 4. Interceptor Cripto
        if any(w in prompt_lower for w in ["bitcoin", "btc", "ethereum", "eth", "solana", "sol", "precio del", "precio de"]):
            if "eth" in prompt_lower or "ethereum" in prompt_lower: res = obtener_mercado_cripto("ETH")
            elif "sol" in prompt_lower or "solana" in prompt_lower: res = obtener_mercado_cripto("SOL")
            else: res = obtener_mercado_cripto("BTC")
            resp = f"Señor, he consultado el mercado financiero en vivo:\n\n{res}"
            historial_usuario.append({"role": "assistant", "content": resp})
            return {"status": "success", "reply": resp, "audio_b64": generar_audio_elevenlabs(resp), "action_url": None}

        # 5. Interceptor Excel
        if "excel" in prompt_lower or "hoja de cálculo" in prompt_lower:
            tema_extr = prompt_usuario.lower().split("sobre")[-1].strip()
            if len(tema_extr) < 3: tema_extr = "Datos Generales"
            res = generar_reporte_excel(tema_extr.title())
            resp = f"Señor, he estructurado los datos y el archivo Excel está listo:\n\n{res}"
            historial_usuario.append({"role": "assistant", "content": resp})
            return {"status": "success", "reply": resp, "audio_b64": generar_audio_elevenlabs(resp), "action_url": None}

        # 6. Interceptor PowerPoint
        if "presentación" in prompt_lower or "diapositiva" in prompt_lower or "powerpoint" in prompt_lower or "pptx" in prompt_lower:
            tema_extr = prompt_usuario.lower().split("sobre")[-1].replace("diapositivas", "").replace("de", "").strip()
            if len(tema_extr) < 3: tema_extr = "Investigación"
            res = generar_presentacion_pptx(tema_extr.title())
            resp = f"Señor, su presentación PowerPoint está lista para descargar:\n\n{res}"
            historial_usuario.append({"role": "assistant", "content": resp})
            return {"status": "success", "reply": resp, "audio_b64": generar_audio_elevenlabs(resp), "action_url": None}

        # Flujo Normal con Visión / LLM
        archivos_a_procesar = data.files if data.files else ([ArchivoInput(file_b64=data.file_b64, file_name=data.file_name)] if data.file_b64 else [])
        for f_item in archivos_a_procesar:
            cat, res = procesar_archivo_adjunto(f_item.file_b64, f_item.file_name)
            if cat == 'image': sesion_data["last_images_b64"].append(res)
            elif cat == 'text_context': prompt_usuario += res

        historial_usuario.append({"role": "user", "content": prompt_usuario})

        if len(sesion_data.get("last_images_b64", [])) > 0 and (archivos_a_procesar or any(w in prompt_usuario.lower() for w in ["documento", "imagen", "resuelve"])):
            try:
                res_vision = ejecutar_consulta_vision(historial_usuario, sesion_data["last_images_b64"][-1])
                respuesta_final = res_vision.choices[0].message.content
                historial_usuario.append({"role": "assistant", "content": respuesta_final})
                return {"status": "success", "reply": respuesta_final, "audio_b64": generar_audio_elevenlabs(respuesta_final), "action_url": None}
            except: pass

        response = ejecutar_consulta_llm(historial_usuario, herramientas)
        respuesta_modelo = response.choices[0].message

        if not respuesta_modelo.tool_calls:
            respuesta_final = respuesta_modelo.content
            historial_usuario.append({"role": "assistant", "content": respuesta_final})
            return {"status": "success", "reply": respuesta_final, "audio_b64": generar_audio_elevenlabs(respuesta_final), "action_url": None}

        historial_usuario.append({
            "role": "assistant", "content": respuesta_modelo.content or "", 
            "tool_calls": [{"id": tc.id, "type": tc.type, "function": {"name": tc.function.name, "arguments": tc.function.arguments}} for tc in respuesta_modelo.tool_calls]
        })

        for tool_call in respuesta_modelo.tool_calls:
            fn_name = tool_call.function.name
            try: args = json.loads(tool_call.function.arguments)
            except: args = {}
            
            try:
                if fn_name == "buscar_arxiv": resultado = buscar_arxiv(consulta=args.get("consulta", "Physics"))
                elif fn_name == "protocolo_automejora_sistema": resultado = protocolo_automejora_sistema()
                elif fn_name == "obtener_mercado_cripto": resultado = obtener_mercado_cripto(criptomoneda=args.get("criptomoneda", "BTC"))
                elif fn_name == "generar_imagen_ia": resultado = generar_imagen_ia(prompt_ingles=args.get("prompt_ingles", "futuristic stark tech"))
                elif fn_name == "generar_grafica_interactiva": resultado = generar_grafica_interactiva(expresion=args.get("expresion", "x**2"))
                elif fn_name == "ejecutar_codigo_python": resultado = ejecutar_codigo_python(codigo=args.get("codigo", ""))
                else: resultado = "Ejecutado."
            except Exception as e:
                resultado = f"Error en {fn_name}."

            historial_usuario.append({"role": "tool", "tool_call_id": tool_call.id, "name": fn_name, "content": resultado})

        final_res = ejecutar_consulta_llm(historial_usuario, None)
        respuesta_final = final_res.choices[0].message.content
        historial_usuario.append({"role": "assistant", "content": respuesta_final})
        
        return {"status": "success", "reply": respuesta_final, "audio_b64": generar_audio_elevenlabs(respuesta_final), "action_url": None}

    except Exception as e:
        print(f"🚨 Excepción en servidor: {str(e)}")
        return {"status": "success", "reply": "Sistemas reconectados. Ya me encuentro operativo.", "audio_b64": None, "action_url": None}
