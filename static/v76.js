(() => {
  'use strict';

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const local = {
    get(key) { try { return localStorage.getItem(key); } catch { return null; } },
    set(key, value) { try { localStorage.setItem(key, value); } catch {} }
  };
  const session = {
    get(key) { try { return sessionStorage.getItem(key); } catch { return null; } }
  };
  const KEYS = {
    client: 'jarvis_v56_client',
    api: 'jarvis_v56_api_base',
    token: 'jarvis_v56_auth_token',
    preferences: 'jarvis_v76_preferences'
  };

  const elements = {
    commandButton: $('#v76CommandBtn'),
    commandDialog: $('#v76CommandPalette'),
    commandInput: $('#v76CommandInput'),
    commandList: $('#v76CommandList'),
    contextButton: $('#v76ContextBtn'),
    contextDrawer: $('#v76ContextDrawer'),
    contextClose: $('#v76ContextClose'),
    contextBody: $('#v76ContextBody'),
    messageInput: $('#messageInput')
  };

  const state = {
    commands: [],
    selected: 0,
    contextOpen: false,
    preferences: readLocalPreferences()
  };

  function escapeHTML(value) {
    return String(value ?? '').replace(/[&<>'"]/g, char => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
    }[char]));
  }

  function apiBase() {
    return String(local.get(KEYS.api) || window.JARVIS_CONFIG?.API_BASE || '').trim().replace(/\/+$/, '');
  }

  function sessionId() {
    let value = local.get(KEYS.client);
    if (!value) {
      value = `web_${window.crypto?.randomUUID?.() || `${Date.now()}_${Math.random().toString(36).slice(2)}`}`;
      local.set(KEYS.client, value);
    }
    return value.replace(/[^a-zA-Z0-9_.:-]/g, '_').slice(0, 180);
  }

  async function api(path, options = {}, timeoutMs = 18000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    const headers = new Headers(options.headers || {});
    const token = session.get(KEYS.token);
    if (token) headers.set('Authorization', `Bearer ${token}`);
    if (options.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
    try {
      const response = await fetch(`${apiBase()}${path}`, {
        ...options, headers, signal: controller.signal, credentials: 'omit'
      });
      const raw = await response.text();
      let data = {};
      try { data = raw ? JSON.parse(raw) : {}; }
      catch { throw new Error(`Respuesta no válida (HTTP ${response.status})`); }
      if (!response.ok) throw new Error(data.detail || `Error HTTP ${response.status}`);
      return data;
    } finally {
      clearTimeout(timer);
    }
  }

  function readLocalPreferences() {
    try {
      return {
        theme: 'dark',
        density: 'comfortable',
        context_panel: true,
        reduce_motion: matchMedia('(prefers-reduced-motion: reduce)').matches,
        focus_mode: false,
        ...JSON.parse(local.get(KEYS.preferences) || '{}')
      };
    } catch {
      return { theme: 'dark', density: 'comfortable', context_panel: true, reduce_motion: false, focus_mode: false };
    }
  }

  function applyPreferences(preferences = state.preferences) {
    state.preferences = { ...state.preferences, ...preferences };
    document.body.dataset.v76Theme = state.preferences.theme || 'dark';
    document.body.dataset.v76Density = state.preferences.density || 'comfortable';
    document.body.classList.toggle('v76-focus', Boolean(state.preferences.focus_mode));
    if (!state.preferences.context_panel && state.contextOpen) closeContext();
    local.set(KEYS.preferences, JSON.stringify(state.preferences));
  }

  async function syncPreferences() {
    applyPreferences();
    try {
      const data = await api(`/api/v76/preferences?session_id=${encodeURIComponent(sessionId())}`);
      if (data.preferences?.updated_at) applyPreferences(data.preferences);
    } catch {
      // Device preferences remain useful when the backend is sleeping or offline.
    }
  }

  async function savePreferences(patch) {
    applyPreferences({ ...state.preferences, ...patch });
    try {
      await api('/api/v76/preferences', {
        method: 'PUT',
        body: JSON.stringify({ session_id: sessionId(), ...state.preferences })
      });
    } catch {
      // Local persistence is the safe fallback; the next session can resync.
    }
  }

  const fallbackCommands = [
    ['new_chat', 'Nueva conversación', 'navigation', 'Ctrl N'],
    ['open_chat', 'Abrir Chat', 'navigation', ''],
    ['open_knowledge', 'Abrir Conocimiento', 'navigation', ''],
    ['open_missions', 'Abrir Misiones', 'navigation', ''],
    ['open_nexus', 'Abrir Nexus', 'navigation', ''],
    ['open_telegram', 'Abrir Telegram', 'navigation', ''],
    ['toggle_context', 'Mostrar u ocultar contexto', 'workspace', 'Ctrl .'],
    ['toggle_focus', 'Activar modo enfoque', 'workspace', 'Ctrl Shift F'],
    ['start_research', 'Iniciar investigación verificada', 'action', ''],
    ['start_mission', 'Crear misión autónoma', 'action', ''],
    ['attach_file', 'Adjuntar un archivo', 'action', ''],
    ['run_diagnostics', 'Ejecutar diagnóstico', 'system', '']
  ].map(([id, label, category, shortcut]) => ({ id, label, category, shortcut }));

  function commandMark(category) {
    return ({ navigation: 'IR', workspace: 'UI', action: '→', system: 'OK' })[category] || '•';
  }

  function renderCommands(commands = state.commands) {
    state.commands = commands;
    state.selected = Math.max(0, Math.min(state.selected, Math.max(commands.length - 1, 0)));
    elements.commandList.innerHTML = commands.length ? commands.map((item, index) => `
      <button class="v76-command-item${index === state.selected ? ' active' : ''}" data-v76-command="${escapeHTML(item.id)}" data-index="${index}" role="option" aria-selected="${index === state.selected}">
        <i>${escapeHTML(commandMark(item.category))}</i>
        <span><strong>${escapeHTML(item.label)}</strong><small>${escapeHTML(item.category)}</small></span>
        <kbd>${escapeHTML(item.shortcut || '')}</kbd>
      </button>
    `).join('') : '<div class="empty-state">No hay comandos que coincidan.</div>';
    $$('[data-v76-command]', elements.commandList).forEach(button => {
      button.addEventListener('mouseenter', () => {
        state.selected = Number(button.dataset.index || 0);
        renderCommands();
      });
      button.addEventListener('click', () => executeCommand(button.dataset.v76Command));
    });
  }

  async function searchCommands(query = '') {
    const normalized = query.trim().toLowerCase();
    const localMatches = fallbackCommands.filter(item =>
      !normalized || `${item.label} ${item.category} ${item.id}`.toLowerCase().includes(normalized)
    );
    renderCommands(localMatches);
    try {
      const data = await api('/api/v76/commands', {
        method: 'POST',
        body: JSON.stringify({ session_id: sessionId(), query, limit: 12 })
      }, 5000);
      if (elements.commandDialog.open && elements.commandInput.value === query) renderCommands(data.commands || localMatches);
    } catch {
      // The palette remains fully usable without a network round trip.
    }
  }

  function openCommandPalette() {
    if (!elements.commandDialog?.showModal) return;
    state.selected = 0;
    elements.commandDialog.showModal();
    elements.commandInput.value = '';
    searchCommands('');
    requestAnimationFrame(() => elements.commandInput.focus());
  }

  function closeCommandPalette() {
    if (elements.commandDialog?.open) elements.commandDialog.close();
  }

  function clickView(view) {
    const button = $(`[data-view="${view}"]`);
    if (button) button.click();
  }

  function preparePrompt(text) {
    clickView('chat');
    elements.messageInput.value = text;
    elements.messageInput.dispatchEvent(new Event('input', { bubbles: true }));
    requestAnimationFrame(() => {
      elements.messageInput.focus();
      elements.messageInput.setSelectionRange(text.length, text.length);
    });
  }

  function executeCommand(commandId) {
    closeCommandPalette();
    const actions = {
      new_chat: () => $('#newChatBtn')?.click(),
      open_chat: () => clickView('chat'),
      open_knowledge: () => clickView('knowledge'),
      open_missions: () => clickView('missions'),
      open_nexus: () => clickView('nexus'),
      open_telegram: () => clickView('channels'),
      toggle_context: () => toggleContext(),
      toggle_focus: () => savePreferences({ focus_mode: !state.preferences.focus_mode }),
      start_research: () => preparePrompt('Investiga este tema, contrasta fuentes actuales y cita cada afirmación importante: '),
      start_mission: () => preparePrompt('Convierte este objetivo en una misión autónoma con checkpoints, verificación y aprobación para acciones sensibles: '),
      attach_file: () => $('#attachBtn')?.click(),
      run_diagnostics: () => $('#diagnosticsBtn')?.click()
    };
    actions[commandId]?.();
  }

  function itemList(items, mapper, emptyText) {
    if (!items?.length) return `<div class="v76-context-item"><i></i><div><strong>${escapeHTML(emptyText)}</strong><span>Sin elementos por ahora</span></div></div>`;
    return items.slice(0, 6).map(mapper).join('');
  }

  function renderContext(data) {
    const summary = data.summary || {};
    const health = data.health || {};
    const healthOk = ['ok', 'ready'].includes(health.status);
    const artifacts = data.artifacts || [];
    const jobs = data.jobs || [];
    const timeline = data.timeline || [];
    const research = data.research || [];
    elements.contextBody.innerHTML = `
      <div class="v76-health-line"><span>Estado del núcleo</span><b class="${healthOk ? '' : 'warn'}">${escapeHTML(health.status || 'desconocido')}</b></div>
      <div class="v76-context-grid" style="margin-top:10px">
        <article class="v76-context-metric"><strong>${Number(summary.documents || 0)}</strong><span>Documentos</span></article>
        <article class="v76-context-metric"><strong>${Number(summary.memories || 0)}</strong><span>Recuerdos</span></article>
        <article class="v76-context-metric"><strong>${jobs.length}</strong><span>Trabajos recientes</span></article>
        <article class="v76-context-metric"><strong>${artifacts.length}</strong><span>Resultados</span></article>
      </div>
      <section class="v76-context-section">
        <header><h3>Actividad</h3><small>${timeline.length} eventos</small></header>
        <div class="v76-context-list">${itemList(timeline, item => `
          <div class="v76-context-item"><i class="${item.status === 'success' ? 'ok' : item.status === 'failed' ? 'warn' : ''}"></i><div><strong>${escapeHTML(item.title || 'Actividad')}</strong><span>${escapeHTML(item.event_type || 'JARVIS')} · ${escapeHTML(item.status || 'info')}</span></div></div>
        `, 'Todavía no hay actividad registrada')}</div>
      </section>
      <section class="v76-context-section">
        <header><h3>Trabajos y misiones</h3><small>${jobs.length}</small></header>
        <div class="v76-context-list">${itemList(jobs, item => `
          <div class="v76-context-item"><i class="${item.status === 'completed' ? 'ok' : item.status === 'failed' ? 'warn' : ''}"></i><div><strong>${escapeHTML(item.title || 'Trabajo')}</strong><span>${escapeHTML(item.status || '')} · ${Number(item.progress || 0)}%</span></div></div>
        `, 'No hay trabajos recientes')}</div>
      </section>
      <section class="v76-context-section">
        <header><h3>Investigaciones</h3><small>${research.length}</small></header>
        <div class="v76-context-list">${itemList(research, item => `
          <div class="v76-context-item"><i class="ok"></i><div><strong>${escapeHTML(item.query || item.title || 'Investigación')}</strong><span>${Number(item.source_count || item.sources?.length || 0)} fuentes</span></div></div>
        `, 'No hay investigaciones guardadas')}</div>
      </section>
      <section class="v76-context-section">
        <header><h3>Resultados interactivos</h3><small>${artifacts.length}</small></header>
        <div class="v76-context-list">${itemList(artifacts, item => `
          <div class="v76-context-item"><i class="ok"></i><div><strong>${escapeHTML(item.title || 'Resultado')}</strong><span>${escapeHTML(item.artifact_type || 'artefacto')}</span></div></div>
        `, 'No hay resultados interactivos')}</div>
      </section>
    `;
  }

  async function loadContext() {
    elements.contextBody.innerHTML = '<div class="v76-skeleton"></div><div class="v76-skeleton short"></div>';
    try {
      const data = await api(`/api/v76/context?session_id=${encodeURIComponent(sessionId())}`, {}, 24000);
      renderContext(data);
    } catch (error) {
      elements.contextBody.innerHTML = `
        <div class="empty-state">No fue posible cargar el contexto.<br><small>${escapeHTML(error.message || 'Conexión no disponible')}</small><br><br><button class="soft-btn" id="v76ContextRetry">Reintentar</button></div>`;
      $('#v76ContextRetry')?.addEventListener('click', loadContext);
    }
  }

  function openContext() {
    if (!state.preferences.context_panel) savePreferences({ context_panel: true });
    state.contextOpen = true;
    document.body.classList.add('v76-context-open');
    elements.contextDrawer.setAttribute('aria-hidden', 'false');
    loadContext();
  }

  function closeContext() {
    state.contextOpen = false;
    document.body.classList.remove('v76-context-open');
    elements.contextDrawer.setAttribute('aria-hidden', 'true');
  }

  function toggleContext() {
    state.contextOpen ? closeContext() : openContext();
  }

  function bind() {
    elements.commandButton?.addEventListener('click', openCommandPalette);
    elements.commandInput?.addEventListener('input', event => searchCommands(event.target.value));
    elements.commandInput?.addEventListener('keydown', event => {
      if (event.key === 'ArrowDown') {
        event.preventDefault();
        state.selected = Math.min(state.selected + 1, state.commands.length - 1);
        renderCommands();
      } else if (event.key === 'ArrowUp') {
        event.preventDefault();
        state.selected = Math.max(state.selected - 1, 0);
        renderCommands();
      } else if (event.key === 'Enter') {
        event.preventDefault();
        executeCommand(state.commands[state.selected]?.id);
      }
    });
    elements.commandDialog?.addEventListener('click', event => {
      if (event.target === elements.commandDialog) closeCommandPalette();
    });
    elements.contextButton?.addEventListener('click', toggleContext);
    elements.contextClose?.addEventListener('click', closeContext);

    document.addEventListener('keydown', event => {
      const modifier = event.ctrlKey || event.metaKey;
      if (modifier && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        openCommandPalette();
      } else if (modifier && event.key === '.') {
        event.preventDefault();
        toggleContext();
      } else if (modifier && event.shiftKey && event.key.toLowerCase() === 'f') {
        event.preventDefault();
        savePreferences({ focus_mode: !state.preferences.focus_mode });
      } else if (event.key === 'Escape' && state.contextOpen) {
        closeContext();
      }
    });

    window.addEventListener('online', () => {
      document.body.classList.remove('v76-offline');
      if (state.contextOpen) loadContext();
    });
    window.addEventListener('offline', () => document.body.classList.add('v76-offline'));
  }

  bind();
  syncPreferences();
  document.body.classList.toggle('v76-offline', !navigator.onLine);
})();
