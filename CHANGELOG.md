# Cambios — J.A.R.V.I.S. v18

## Núcleo

- Nuevo módulo `jarvis_core/runtime.py`.
- Caché en memoria y Redis opcional.
- Single-flight para solicitudes concurrentes idénticas.
- Circuit breakers en Groq, proveedores secundarios y búsqueda.
- Compresión de contexto.
- Timeout global de resolución.
- Middleware de trazabilidad y compresión GZip.

## Trabajos

- Checkpoints, intentos y recuperación al reiniciar.
- Pausar, reanudar, cancelar y reintentar.
- Workers configurables.
- Recuperación de trabajos estancados durante mantenimiento.

## Operaciones

- `/api/health/live`.
- `/api/health/ready`.
- `/api/health/deep`.
- `/api/performance`.
- Streaming NDJSON con progreso y heartbeats.
- Mantenimiento periódico de base de datos y caché.

## Interfaz

- Panel de rendimiento y estabilidad.
- Controles de trabajos autónomos.
- Recepción de eventos de progreso en solicitudes largas.
- Recursos PWA y reactor incluidos dentro del paquete.

## Calidad

- Flujo GitHub Actions.
- Pruebas de caché, circuit breaker, contexto, health checks, chat directo, idempotencia, trabajos, rendimiento, recursos y streaming.
