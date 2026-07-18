# Cambios — J.A.R.V.I.S. v19

## Multi-Provider Gateway

- Adaptador estandarizado de proveedores.
- Integración de Groq mediante Chat Completions.
- Integración de OpenAI mediante Responses API.
- Integración de Google Gemini mediante `generateContent`.
- Compatibilidad con servidores adicionales basados en Chat Completions.
- Compatibilidad con Ollama local o remoto.
- Router por intención y modo.
- Puntuación por calidad, velocidad y costo relativo.
- Preferencia explícita de proveedor.
- Fallback entre modelos y proveedores.
- Circuit breaker independiente por proveedor y modelo.
- Métricas de éxito, latencia y uso.
- Endpoint `/api/providers`.
- Endpoint `/api/providers/route-preview`.
- Panel visual de proveedores.
- Laboratorio de enrutamiento sin consumo de tokens.
- Ocultación adicional de claves en mensajes de error.
- Caché de interfaz actualizada a v19.
