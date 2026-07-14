# Instalación paso a paso — J.A.R.V.I.S. MAX v3

## 1. Respalda tu versión actual

Descarga de GitHub los archivos actuales antes de reemplazarlos.

## 2. Sube el proyecto completo

En tu repositorio deben quedar en la raíz:

```text
main.py
requirements.txt
render.yaml
static/index.html
```

No subas `.env` ni una clave de Groq.

## 3. Configura Render

En Environment agrega:

```text
GROQ_API_KEY = tu clave nueva
GROQ_MODEL = llama-3.3-70b-versatile
GROQ_FALLBACK_MODELS = llama-3.1-8b-instant,meta-llama/llama-4-scout-17b-16e-instruct
JARVIS_DB_FILE = jarvis_memory.db
JARVIS_ALLOWED_ORIGINS = *
JARVIS_ACCESS_KEY = una clave privada larga opcional
```

## 4. Revisa los comandos

Build:

```bash
pip install -r requirements.txt
```

Start:

```bash
uvicorn main:app --host 0.0.0.0 --port $PORT
```

Health Check:

```text
/api/health
```

## 5. Despliega

Usa `Manual Deploy → Clear build cache & deploy`.

## 6. Comprueba

Abre:

```text
https://TU-SERVICIO.onrender.com/api/health
https://TU-SERVICIO.onrender.com/api/self-check
https://TU-SERVICIO.onrender.com/api/capabilities
```

Luego abre la raíz del servicio. La interfaz se carga desde el mismo backend.

## 7. Configura la clave de acceso

Si definiste `JARVIS_ACCESS_KEY`, entra en el menú de configuración de la interfaz y escribe exactamente la misma clave.

## 8. Persistencia recomendada

Agrega un Persistent Disk en `/var/data` y cambia:

```text
JARVIS_DB_FILE=/var/data/jarvis_memory.db
```

## 9. Pruebas

- `¿Qué capacidades tienes?`
- `Calcula el 12% de 85000.`
- `Resuelve x² - 5x + 6 = 0 paso a paso.`
- Sube un PDF y solicita un resumen.
- Crea un recuerdo desde el panel Memoria.
- Crea un trabajo desde Trabajos autónomos.
- Abre Centro del sistema y ejecuta el autodiagnóstico.
