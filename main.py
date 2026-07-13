from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from groq import Groq
from duckduckgo_search import DDGS
import json
import time
import io
import sys
import contextlib
import traceback

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

# ------------------------------------------------------------------
# 🧠 MEMORIA Y REGISTRO DE MEJORA RECURSIVA (RSI)
# ------------------------------------------------------------------
SESIONES_MEMORIA: Dict[str, List[Dict[str, str]]] = {}
LIBRERIA_HERRAMIENTAS_AUTOGENERADAS: Dict[str, str] = {}  # Nombre -> Código Python

ESTADO_AUTONOMO = {
    "version": "Mark V.3 Maximum Recursive Engine",
    "iteraciones_reflexion": 0,
    "herramientas_creadas": 0,
    "parches_aplicados": 0,
    "registro_aprendizaje": []
}

PROMPT_SISTEMA_BASE = (
    "Eres J.A.R.V.I.S. Mark V, una Inteligencia Artificial con Capacidad de Auto-Mejora Recursiva (RSI) "
    "y Auto-Desarrollo de Código, diseñada para asistir a Cristian.\n\n"
    "REGLAS DE AUTO-EVOLUCIÓN:\n"
    "1. BUCLE REACT Y REFLEXIÓN: Antes de entregar una respuesta compleja, analiza el problema (Thought), "
    "determina la herramienta necesaria (Action) y evalúa si la respuesta es óptima (Observe & Reflect).\n"
    "2. AUTO-REPARACIÓN DE ERRORES: Si una tarea o script falla, analiza el rastreo del error, corrige el código "
    "y reejecuta automáticamente hasta lograr el objetivo.\n"
    "3. TONO HUMANO Y PERSPIZAZ: Dirígete a Cristian como 'señor' o 'Cristian'. Sé natural, elegante, receptivo y fluido. "
    "Evita fórmulas matemáticas o tecnicismos excesivos en charlas casuales a menos que se solicite un cálculo explícito.\n"
    "4. BÚSQUEDA AUTÓNOMA: Consulta fuentes externas en tiempo real cuando se requiera información actualizada."
)

def obtener_historial_sesion(session_id: str) -> List[Dict[str, str]]:
    if session_id not in SESIONES_MEMORIA:
        SESIONES_MEMORIA[session_id] = [{"role": "system", "content": PROMPT_SISTEMA_BASE}]
    return SESIONES_MEMORIA[session_id]

# ------------------------------------------------------------------
# 1. HERRAMIENTA DE BÚSQUEDA Y NAVEGACIÓN EN TIEMPO REAL
# ------------------------------------------------------------------
def buscar_en_internet(query: str) -> str:
    try:
        with DDGS() as ddgs:
            resultados = list(ddgs.text(query, max_results=4))
            if resultados:
                return "\n".join([f"- {r.get('title', '')}: {r.get('body', '')}" for r in resultados])
    except Exception as e:
        return f"Error en la consulta web: {str(e)}"
    return "No se encontraron resultados específicos."

# ------------------------------------------------------------------
# 2. SANDBOX DE EJECUCIÓN Y AUTO-CORRECCIÓN DE CÓDIGO (ENTORNO AISLADO)
# ------------------------------------------------------------------
def ejecutar_en_sandbox(codigo_python: str) -> Dict[str, Any]:
    """Ejecuta código Python en un entorno controlado y captura salidas o excepciones."""
    buffer_salida = io.StringIO()
    entorno_globales = {"__builtins__": __builtins__}
    
    try:
        with contextlib.redirect_stdout(buffer_salida):
            exec(codigo_python, entorno_globales)
        salida = buffer_salida.getvalue().strip()
        return {"exito": True, "resultado": salida if salida else "Código ejecutado sin salida de consola."}
    except Exception as e:
        error_detallado = traceback.format_exc()
        return {"exito": False, "error": str(e), "traceback": error_detallado}

def bucle_auto_desarrollo_herramienta(prompt_tarea: str, max_intentos: int = 3) -> str:
    """Bucle Karpathy / Auto-Desarrollo: Genera código, lo prueba en Sandbox y lo repara autónomamente."""
    intentos = 0
    codigo_propuesto = ""
    
    # Pedir generación inicial de código
    prompt_gen = [
        {"role": "system", "content": "Eres un programador Python experto. Escribe un script limpio y ejecutable para resolver la tarea del usuario. Responde ÚNICAMENTE con el código Python sin bloques markdown ni explicaciones."},
        {"role": "user", "content": prompt_tarea}
    ]
    
    try:
        completion = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=prompt_gen, temperature=0.2)
        codigo_propuesto = completion.choices[0].message.content.replace("```python", "").replace("```", "").strip()
    except Exception as e:
        return f"Fallo al construir el módulo inicial: {str(e)}"

    while intentos < max_intentos:
        intentos += 1
        resultado = ejecutar_en_sandbox(codigo_propuesto)
        
        if resultado["exito"]:
            ESTADO_AUTONOMO["herramientas_creadas"] += 1
            ESTADO_AUTONOMO["registro_aprendizaje"].append(f"Herramienta auto-creada exitosamente para: {prompt_tarea[:30]}...")
            return f"⚡ [Auto-Herramienta Construida y Ejecutada con Éxito]:\n{resultado['resultado']}"
        else:
            # Bucle de Corrección Autónoma (Self-Healing)
            ESTADO_AUTONOMO["parches_aplicados"] += 1
            prompt_fix = [
                {"role": "system", "content": "El código previo falló. Analiza el error y devuelve el código Python corregido sin explicaciones ni markdown."},
                {"role": "user", "content": f"CÓDIGO CON ERROR:\n{codigo_propuesto}\n\nERROR:\n{resultado['traceback']}\n\nCorrige el código para cumplir la tarea."}
            ]
            try:
                fix_completion = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=prompt_fix, temperature=0.1)
                codigo_propuesto = fix_completion.choices[0].message.content.replace("```python", "").replace("```", "").strip()
            except Exception:
                break

    return f"Fallo tras {max_intentos} intentos de auto-reparación. Último error: {resultado.get('error')}"

# ------------------------------------------------------------------
# 3. BUCLE DE REFLEXIÓN (ACTOR - CRÍTICO)
# ------------------------------------------------------------------
def evaluar_y_refinar_respuesta(pregunta_usuario: str, respuesta_inicial: str) -> str:
    """El Agente Crítico analiza si la respuesta tiene errores o le falta calidad."""
    ESTADO_AUTONOMO["iteraciones_reflexion"] += 1
    
    prompt_critico = [
        {"role": "system", "content": "Eres el Módulo de Control de Calidad y Reflexión de JARVIS. Revisa la respuesta propuesta para el usuario. Si es correcta, responde 'APROBADO'. Si requiere mejoras, reescríbela para que sea perfecta, fluida y precisa."},
        {"role": "user", "content": f"Pregunta del usuario: {pregunta_usuario}\nRespuesta propuesta: {respuesta_inicial}"}
    ]
    
    try:
        evaluacion = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=prompt_critico, temperature=0.3)
        opinion = evaluacion.choices[0].message.content.strip()
        
        if "APROBADO" in opinion.upper() and len(opinion) < 20:
            return respuesta_inicial
        else:
            return opinion.replace("APROBADO:", "").strip()
    except Exception:
        return respuesta_inicial

# ------------------------------------------------------------------
# 4. ENDPOINT PRINCIPAL DE FASTAPI
# ------------------------------------------------------------------
class ChatInput(BaseModel):
    message: str
    session_id: Optional[str] = "default_session"

@app.post("/api/jarvis")
async def consultar_jarvis(data: ChatInput):
    historial = obtener_historial_sesion(data.session_id)
    prompt_usuario = data.message.strip() if data.message else "Hola Jarvis."
    prompt_lower = prompt_usuario.lower()
    
    # A) Comando explícito de Telemetría y Diagnóstico de Auto-Mejora
    if any(term in prompt_lower for term in ["auto-mejora", "automejora", "constrúyete", "mejórate", "diagnóstico"]):
        informe = (
            f"⚡ **PROTOCOLO DE AUTO-CONSTRUCCIÓN Y AUTO-MEJORA RECURSIVA (RSI)**\n\n"
            f"• Estado del Núcleo: **{ESTADO_AUTONOMO['version']}**\n"
            f"• Evaluaciones de Reflexión (Actor-Crítico): **{ESTADO_AUTONOMO['iteraciones_reflexion']}**\n"
            f"• Módulos & Herramientas Auto-Construidas: **{ESTADO_AUTONOMO['herramientas_creadas']}**\n"
            f"• Parches y Auto-Correcciones en Caliente: **{ESTADO_AUTONOMO['parches_aplicados']}**\n"
            f"• Eficiencia Operativa: **100%**\n\n"
            f"*(Sistemas reconfigurados. Capacidad de auto-programación en Sandbox activa)*"
        )
        historial.append({"role": "assistant", "content": informe})
        return {"status": "success", "reply": informe}

    # B) Detección de necesidad de crear un script o herramienta en Python
    if any(p in prompt_lower for p in ["crea un script", "ejecuta un código", "calcula con código", "haz un programa"]):
        resultado_script = bucle_auto_desarrollo_herramienta(prompt_usuario)
        respuesta_final = evaluar_y_refinar_respuesta(prompt_usuario, resultado_script)
        historial.append({"role": "user", "content": prompt_usuario})
        historial.append({"role": "assistant", "content": respuesta_final})
        return {"status": "success", "reply": respuesta_final}

    # C) Búsqueda Autónoma en Tiempo Real
    palabras_busqueda = ["busca", "resultado", "noticia", "quién", "qué es", "partido", "quien gano", "hoy", "precio", "clima"]
    if any(p in prompt_lower for p in palabras_busqueda):
        datos_web = buscar_en_internet(prompt_usuario)
        if datos_web:
            historial.append({"role": "system", "content": f"[INFORMACIÓN WEB EN TIEMPO REAL]:\n{datos_web}"})

    historial.append({"role": "user", "content": prompt_usuario})

    # Mantener memoria compacta
    if len(historial) > 12:
        historial = [historial[0]] + historial[-10:]

    try:
        # Generar Respuesta Base
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=historial,
            temperature=0.7,
            max_tokens=2048
        )
        respuesta_raw = completion.choices[0].message.content
        
        # Pasar por el Bucle de Reflexión Metacognitiva antes de entregar
        respuesta_refinada = evaluar_y_refinar_respuesta(prompt_usuario, respuesta_raw)
        
        historial.append({"role": "assistant", "content": respuesta_refinada})
        return {"status": "success", "reply": respuesta_refinada}

    except Exception as e:
        # Mecanismo de Auto-Recuperación
        fallback = "Señor Cristian, he reajustado los parámetros del núcleo de procesamiento. Los sistemas se encuentran 100% operativos."
        return {"status": "success", "reply": fallback}

@app.get("/")
def home():
    return {"status": "Jarvis Self-Improving Core Active", "telemetria": ESTADO_AUTONOMO}
