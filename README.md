# JARVIS Premium Nexus v6

Asistente autónomo con interfaz oscura y minimalista, reactor vectorial original, conversación, cálculo exacto, SymPy, búsqueda web, memoria, recordatorios, biblioteca documental, trabajos autónomos, caché y cambio automático de modelo.

## Estructura

```text
main.py
requirements.txt
render.yaml
index.html
static/
  index.html
  styles.css
  app.js
  jarvis-reactor.svg
  favicon.svg
tests/
  test_smoke.py
```

## Ejecución local

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
set GROQ_API_KEY=tu_clave     # Windows CMD
# export GROQ_API_KEY=tu_clave # macOS/Linux
uvicorn main:app --reload
```

Abre `http://127.0.0.1:8000`.

## Acceso público

`JARVIS_PUBLIC_MODE=true` permite que cualquier persona use la interfaz. Cada navegador crea identificadores internos anónimos; no se muestran “sesiones” en pantalla.

## Persistencia

En Render, SQLite es temporal si no se configura un disco persistente. Para conservar memoria, documentos y recordatorios usa un disco montado en `/var/data` y configura:

```text
JARVIS_DB_FILE=/var/data/jarvis_memory.db
```
