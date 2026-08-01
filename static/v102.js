(() => {
  'use strict';

  const $ = selector => document.querySelector(selector);
  const $$ = selector => [...document.querySelectorAll(selector)];
  const storage = {
    get(key, fallback = '') { try { return localStorage.getItem(key) ?? fallback; } catch (_) { return fallback; } },
    set(key, value) { try { localStorage.setItem(key, value); } catch (_) {} },
  };

  const state = { open: false, status: null, hub: null };
  const elements = {};

  document.addEventListener('DOMContentLoaded', init);

  function init() {
    Object.assign(elements, {
      drawer: $('#v102ToolsDrawer'), close: $('#v102ToolsClose'), scrim: $('#scrim'),
      projectLabel: $('#v102ProjectLabel'), projectSelect: $('#projectSelect'),
      artifacts: $('#v102ArtifactCount'), memories: $('#v102MemoryCount'),
      tasks: $('#v102TaskCount'), issues: $('#v102IssueCount'),
    });
    if (!elements.drawer || !window.JARVIS_APP) return;
    restorePreferences();
    bind();
    refreshStatus();
  }

  function restorePreferences() {
    const theme = storage.get('jarvis_v102_theme', 'dark');
    document.documentElement.dataset.theme = theme === 'light' ? 'light' : 'dark';
    const focus = storage.get('jarvis_v102_focus', 'false') === 'true';
    document.body.classList.toggle('v102-focus', focus);
  }

  function bind() {
    $$('.v102-tools-trigger').forEach(button => button.addEventListener('click', toggle));
    elements.close?.addEventListener('click', close);
    elements.scrim?.addEventListener('click', () => { if (state.open) close(); });
    elements.drawer.addEventListener('click', event => {
      const button = event.target.closest('[data-v102-action]');
      if (button) execute(button.dataset.v102Action);
    });
    elements.projectSelect?.addEventListener('change', () => state.open && refreshHub());
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' && state.open) close();
      if ((event.ctrlKey || event.metaKey) && event.shiftKey && event.key.toLowerCase() === 'l') {
        event.preventDefault(); execute('theme');
      }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'b') {
        event.preventDefault(); execute('focus');
      }
    });
  }

  function toggle() { state.open ? close() : open(); }

  function open() {
    state.open = true;
    document.body.classList.add('v102-tools-open');
    elements.drawer.setAttribute('aria-hidden', 'false');
    elements.close?.focus({ preventScroll: true });
    refreshStatus();
  }

  function close() {
    state.open = false;
    document.body.classList.remove('v102-tools-open');
    elements.drawer.setAttribute('aria-hidden', 'true');
  }

  function execute(action) {
    const app = window.JARVIS_APP;
    if (!app) return;
    if (action === 'upload') {
      close(); $('#fileInput')?.click();
    } else if (action === 'research') {
      close(); app.setMode('research'); app.setPrompt('Investiga este tema, contrasta fuentes confiables y cita cada afirmación importante: ');
    } else if (action === 'canvas') {
      close(); $('#v100WorkspaceBtn')?.click();
    } else if (action === 'knowledge') {
      close(); app.openView('knowledge');
    } else if (action === 'missions') {
      close(); app.openView('missions');
    } else if (action === 'voice') {
      close(); $('#voiceBtn')?.click();
    } else if (action === 'quality') {
      close(); app.openView('nexus');
    } else if (action === 'telegram') {
      close(); app.openView('channels');
    } else if (action === 'theme') {
      const light = document.documentElement.dataset.theme !== 'light';
      document.documentElement.dataset.theme = light ? 'light' : 'dark';
      storage.set('jarvis_v102_theme', light ? 'light' : 'dark');
      app.toast(light ? 'Apariencia clara activada' : 'Apariencia oscura activada');
    } else if (action === 'focus') {
      const active = !document.body.classList.contains('v102-focus');
      document.body.classList.toggle('v102-focus', active);
      storage.set('jarvis_v102_focus', String(active));
      app.toast(active ? 'Modo enfoque activado' : 'Modo enfoque desactivado');
    }
  }

  async function refreshStatus() {
    try {
      const sid = encodeURIComponent(window.JARVIS_APP.backendSessionId());
      state.status = await window.JARVIS_APP.request(`/api/v102/status?session_id=${sid}`, {}, { timeoutMs: 16000 });
      renderStates();
    } catch (_) {
      state.status = null;
      renderStates();
    }
    await refreshHub();
  }

  async function refreshHub() {
    const project = window.JARVIS_APP.project || 'General';
    if (elements.projectLabel) elements.projectLabel.textContent = `Proyecto ${project}`;
    try {
      const sid = encodeURIComponent(window.JARVIS_APP.backendSessionId());
      const name = encodeURIComponent(project);
      state.hub = await window.JARVIS_APP.request(`/api/v102/hub?session_id=${sid}&project_name=${name}`, {}, { timeoutMs: 16000 });
    } catch (_) {
      state.hub = null;
    }
    renderCounts();
  }

  function renderStates() {
    $$('[data-v102-state]').forEach(dot => {
      const area = state.status?.areas?.[dot.dataset.v102State];
      dot.className = area?.available ? 'available' : area?.degraded ? 'degraded' : '';
      dot.title = area?.available ? 'Disponible' : area?.degraded ? 'Modo limitado disponible' : 'Requiere conexión o configuración';
    });
  }

  function renderCounts() {
    const counts = state.hub?.counts || {};
    if (elements.artifacts) elements.artifacts.textContent = String(counts.artifacts ?? '—');
    if (elements.memories) elements.memories.textContent = String(counts.memories ?? '—');
    if (elements.tasks) elements.tasks.textContent = String(counts.tasks ?? '—');
    if (elements.issues) elements.issues.textContent = String(counts.open_issues ?? '—');
  }
})();
