# Validación realizada

- `python -m py_compile main.py`: aprobado.
- `node --check` sobre el JavaScript de la interfaz: aprobado.
- `node --check whatsapp/whatsapp_bot.js`: aprobado.
- 5 pruebas unitarias: aprobadas.
- Endpoints `/api/health`, `/api/self-check` y `/`: comprobados con servidor local.
- Renderizado visual probado a 1440 × 960 y 390 × 844.
- Verificación de seguridad: no se incluyeron claves Groq ni credenciales en el proyecto.

Las pruebas externas con Groq requieren que el usuario configure una clave válida y dependen de la cuota y disponibilidad del proveedor.
