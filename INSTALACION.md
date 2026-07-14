# Instalación en GitHub y Render

## 1. Subir a GitHub

Extrae el ZIP y sube **el contenido interior** a la raíz del repositorio. `main.py` debe quedar directamente en la raíz.

## 2. Variables en Render

En **Environment** agrega:

```text
GROQ_API_KEY=tu_clave_nueva
GROQ_MODEL=llama-3.3-70b-versatile
GROQ_FALLBACK_MODELS=llama-3.1-8b-instant
JARVIS_PUBLIC_MODE=true
JARVIS_ALLOWED_ORIGINS=*
JARVIS_REQUESTS_PER_MINUTE=20
JARVIS_DIRECT_ROUTES=true
JARVIS_HISTORY_MESSAGES=10
JARVIS_MAX_COMPLETION_TOKENS=1200
JARVIS_CACHE_TTL_SECONDS=3600
JARVIS_DB_FILE=jarvis_memory.db
```

No escribas la clave de Groq dentro de `main.py` ni la subas a GitHub.

## 3. Comandos de Render

**Build Command**

```bash
pip install -r requirements.txt
```

**Start Command**

```bash
uvicorn main:app --host 0.0.0.0 --port $PORT
```

**Health Check Path**

```text
/api/health
```

## 4. Desplegar

En Render usa:

```text
Manual Deploy → Clear build cache & deploy
```

Cuando el servicio indique **Live**, abre la URL principal. La interfaz y el backend se sirven desde el mismo dominio, por lo que no necesitas GitHub Pages.

## 5. Comprobar

Abre:

```text
TU_URL/api/health
TU_URL/api/self-check
TU_URL/api/capabilities
```

Después prueba en el chat:

```text
Calcula el 12% de 85,000.
Resuelve x² - 5x + 6 = 0 paso a paso.
```

## 6. Disco persistente opcional

Crea un disco en `/var/data` y cambia:

```text
JARVIS_DB_FILE=/var/data/jarvis_memory.db
```
