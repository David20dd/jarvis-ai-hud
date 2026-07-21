name: JARVIS Quality Gate

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  validate:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: pip
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt pytest
      - name: Compile backend
        run: python -m py_compile main.py jarvis_core/runtime.py jarvis_core/professional.py jarvis_core/providers/*.py
      - name: Validate frontend JavaScript
        run: node --check static/app.js
      - name: Run tests
        env:
          JARVIS_DB_FILE: jarvis_ci.db
          JARVIS_PUBLIC_MODE: 'true'
          GROQ_API_KEY: ''
        run: pytest -q
