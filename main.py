GROQ_API_KEY=
GROQ_MODEL=llama-3.3-70b-versatile
GROQ_FALLBACK_MODELS=llama-3.1-8b-instant

JARVIS_PUBLIC_MODE=true
JARVIS_ACCESS_KEY=
JARVIS_ALLOWED_ORIGINS=*
JARVIS_REQUESTS_PER_MINUTE=20
JARVIS_DIRECT_ROUTES=true
JARVIS_HISTORY_MESSAGES=12
JARVIS_MAX_COMPLETION_TOKENS=1400
JARVIS_CACHE_TTL_SECONDS=3600
JARVIS_DB_FILE=jarvis_memory.db

# Identidad privada recomendada. El primer usuario creado será administrador.
JARVIS_AUTH_REQUIRED=true
JARVIS_REGISTRATION_ENABLED=false
JARVIS_AUTH_SESSION_DAYS=30

# Resiliencia y rendimiento
JARVIS_MAX_RESOLUTION_ATTEMPTS=5
JARVIS_WEB_SEARCH_ATTEMPTS=3
JARVIS_WEB_SEARCH_RESULTS=10
JARVIS_PROVIDER_TIMEOUT_SECONDS=45
JARVIS_REQUEST_TIMEOUT_SECONDS=120
JARVIS_VERIFY_RESULTS=true
JARVIS_ALWAYS_RETURN_RESULT=true
JARVIS_CONTEXT_MAX_CHARS=60000
JARVIS_L1_CACHE_ITEMS=512
JARVIS_CIRCUIT_FAILURE_THRESHOLD=3
JARVIS_CIRCUIT_RECOVERY_SECONDS=45
JARVIS_METRICS_SAMPLES=500

# Trabajos persistentes dentro de la instancia web
JARVIS_JOB_WORKERS=2
JARVIS_JOB_MAX_ATTEMPTS=3
JARVIS_JOB_RETRY_BASE_SECONDS=4

# Redis es opcional. Si queda vacío, JARVIS usa memoria + SQLite.
JARVIS_REDIS_URL=

# Multi-Provider Gateway. Configura solo los proveedores que utilizarás.
# Mantén todas las claves exclusivamente en Render o en el servidor.
OPENAI_API_KEY=
OPENAI_MODELS=
OPENAI_BASE_URL=https://api.openai.com/v1

GEMINI_API_KEY=
GEMINI_MODELS=
GEMINI_API_VERSION=v1beta

# Anthropic Claude. Consulta /v1/models en tu cuenta para confirmar modelos disponibles.
ANTHROPIC_API_KEY=
ANTHROPIC_MODELS=claude-sonnet-4-6,claude-haiku-4-5
ANTHROPIC_BASE_URL=https://api.anthropic.com
ANTHROPIC_API_VERSION=2023-06-01
JARVIS_ANTHROPIC_PROMPT_CACHE=true
JARVIS_ANTHROPIC_CACHE_TTL=5m

# Consejo de calidad opcional. Usa un segundo proveedor en tareas complejas y consume más cuota.
JARVIS_CONSENSUS_ENABLED=false
JARVIS_CONSENSUS_INTENTS=research,documents,coding,planning
JARVIS_CONSENSUS_MAX_PROVIDERS=2

# Orden base. El router puede ajustarlo según intención y modo.
JARVIS_PROVIDER_ORDER=groq,anthropic,openai,gemini,compatible,ollama
JARVIS_PROVIDER_MAX_ATTEMPTS=8

# Servidor adicional compatible con Chat Completions.
JARVIS_OPENAI_COMPAT_BASE_URL=
JARVIS_OPENAI_COMPAT_API_KEY=
JARVIS_OPENAI_COMPAT_MODELS=

# Ollama local o en un servidor propio.
JARVIS_OLLAMA_BASE_URL=
JARVIS_OLLAMA_API_KEY=
JARVIS_OLLAMA_MODELS=llama3.1:8b

# Núcleo autónomo v48
# El laboratorio permanece apagado salvo que Docker esté disponible en un host privado.
JARVIS_CODE_LAB_ENABLED=false
JARVIS_CODE_LAB_TIMEOUT_SECONDS=12

# Lista JSON de servidores MCP Streamable HTTP permitidos por el backend.
# Ejemplo: [{"name":"mi-servidor","url":"https://mcp.ejemplo.com/mcp","headers":{"Authorization":"Bearer ..."}}]
# Nunca copies este valor al frontend si contiene credenciales.
JARVIS_MCP_SERVERS_JSON=

# Telegram Bot API. Admite texto, imágenes, notas de voz y documentos.
# Genera secretos largos y limita los chat IDs autorizados.
TELEGRAM_BOT_TOKEN=
TELEGRAM_WEBHOOK_SECRET=
TELEGRAM_ALLOWED_CHAT_IDS=
# Configuración multimedia compartida por Telegram y WhatsApp.
JARVIS_CHANNEL_VISION_MODEL=
JARVIS_CHANNEL_TRANSCRIBE_MODEL=whisper-large-v3-turbo
JARVIS_CHANNEL_MAX_MEDIA_MB=12

# WhatsApp Cloud API oficial de Meta. El canal se limita a atención empresarial.
WHATSAPP_ACCESS_TOKEN=
WHATSAPP_PHONE_NUMBER_ID=
WHATSAPP_VERIFY_TOKEN=
WHATSAPP_APP_SECRET=
WHATSAPP_GRAPH_API_VERSION=
WHATSAPP_ALLOWED_NUMBERS=
WHATSAPP_BUSINESS_NAME=Mi negocio
# Información verdadera que WhatsApp puede usar: servicios, precios, horario, ubicación y políticas.
WHATSAPP_BUSINESS_CONTEXT=
WHATSAPP_HUMAN_CONTACT=
# Palabras comerciales adicionales separadas por comas.
WHATSAPP_BUSINESS_KEYWORDS=
# Alias compatibles de versiones anteriores. Se usan si no defines JARVIS_CHANNEL_*.
WHATSAPP_VISION_MODEL=
WHATSAPP_TRANSCRIBE_MODEL=whisper-large-v3-turbo
WHATSAPP_MAX_MEDIA_MB=12
