# J.A.R.V.I.S. MAX Core v3

Proyecto unificado: FastAPI sirve el backend y la interfaz Stark desde el mismo dominio. Esto elimina errores frecuentes de URL, CORS y versiones desincronizadas entre frontend y backend.

## Capacidades incluidas

- Enrutamiento entre varios modelos Groq.
- Circuit breaker y cambio automático ante error 429 o fallos temporales.
- Tool calling local controlado.
- Cálculo seguro y SymPy sin consumo de tokens.
- Búsqueda web, memoria, recordatorios y biblioteca de documentos.
- Trabajos autónomos ligeros en segundo plano.
- Caché de respuestas y registro de uso.
- Panel Stark con telemetría, autodiagnóstico, actividad y propuestas de mejora.
- Dictado mediante Web Speech API cuando el navegador lo permite.
- Diseño adaptable para computadora y celular.

## Instalación local

1. Instala Python 3.11 o superior.
2. Crea un entorno virtual.
3. Instala dependencias:

```bash
pip install -r requirements.txt
```

4. Copia `.env.example` como `.env` o configura las variables en tu terminal.
5. Define `GROQ_API_KEY`.
6. Inicia:

```bash
uvicorn main:app --reload
```

7. Abre `http://127.0.0.1:8000`.

## Despliegue en Render

Sube toda esta carpeta a un repositorio. En Render usa:

- Build Command: `pip install -r requirements.txt`
- Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- Health Check Path: `/api/health`

Variables mínimas:

```text
GROQ_API_KEY=tu_clave
GROQ_MODEL=llama-3.3-70b-versatile
GROQ_FALLBACK_MODELS=llama-3.1-8b-instant,meta-llama/llama-4-scout-17b-16e-instruct
JARVIS_DB_FILE=jarvis_memory.db
JARVIS_ALLOWED_ORIGINS=*
```

Para proteger la cuota agrega `JARVIS_ACCESS_KEY` y coloca la misma clave en la interfaz: menú Configuración.

## Persistencia

El sistema usa SQLite. En Render, para conservar memoria, documentos, trabajos y recordatorios después de nuevos despliegues, conecta un Persistent Disk en `/var/data` y cambia:

```text
JARVIS_DB_FILE=/var/data/jarvis_memory.db
```

## Límites reales

Ningún proveedor ofrece tokens infinitos ni disponibilidad absoluta. Esta versión reduce el impacto mediante modelos alternativos, caché, rutas locales sin tokens, circuit breaker y modo degradado. Los trabajos de `BackgroundTasks` son ligeros; para tareas largas y durables se recomienda un worker separado con Redis/Celery o una cola administrada.

## Automejora segura

J.A.R.V.I.S. registra errores, uso y retroalimentación, y genera propuestas en `/api/improvement/report`. No modifica ni despliega su propio código sin revisión humana. Esa barrera evita que un error automático rompa producción o exponga secretos.
