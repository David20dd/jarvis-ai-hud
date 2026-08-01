(() => {
  'use strict';

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const store = {
    get(key, fallback = '') { try { return localStorage.getItem(key) ?? fallback; } catch { return fallback; } },
    set(key, value) { try { localStorage.setItem(key, value); } catch {} }
  };
  const keys = {
    sidebar: 'jarvis_v104_sidebar', density: 'jarvis_v104_density', font: 'jarvis_v104_font',
    split: 'jarvis_v104_split_canvas'
  };
  const state = { sidebar: 'full', filter: '', results: [], timer: 0, lastQuery: '', split: false };
  const elements = {};

  document.addEventListener('DOMContentLoaded', init);

  function init() {
    if (!window.JARVIS_APP) return;
    Object.assign(elements, {
      sidebar: $('#v104SidebarBtn'), search: $('#v104GlobalSearchBtn'), dialog: $('#v104SearchDialog'),
      close: $('#v104SearchClose'), input: $('#v104SearchInput'), results: $('#v104SearchResults'),
      split: $('#v104SplitCanvas'), canvasClose: $('#v100WorkspaceClose'), progress: $('#v104Progress'),
      thinking: $('#thinking'), thinkingDetail: $('#thinkingDetail'), messages: $('#messages'), project: $('#projectSelect')
    });
    restore();
    bind();
    observeProgress();
    observeRecovery();
    verifyContract();
  }

  function restore() {
    state.sidebar = store.get(keys.sidebar, 'full');
    if (!['full', 'compact', 'hidden'].includes(state.sidebar)) state.sidebar = 'full';
    applySidebar();
    const density = store.get(keys.density, 'comfortable');
    const font = store.get(keys.font, 'normal');
    document.documentElement.dataset.density = density;
    document.documentElement.dataset.fontSize = font;
    activateSetting('density', density);
    activateSetting('font', font);
    state.split = store.get(keys.split, 'false') === 'true' && matchMedia('(min-width: 1181px)').matches;
    document.body.classList.toggle('v104-split-canvas', state.split);
    elements.split?.classList.toggle('active', state.split);
    if (state.split) setTimeout(() => $('#v100WorkspaceBtn')?.click(), 80);
  }

  function bind() {
    elements.sidebar?.addEventListener('click', cycleSidebar);
    elements.search?.addEventListener('click', openSearch);
    elements.close?.addEventListener('click', closeSearch);
    elements.dialog?.addEventListener('click', event => { if (event.target === elements.dialog) closeSearch(); });
    elements.input?.addEventListener('input', () => {
      clearTimeout(state.timer);
      state.timer = setTimeout(search, 260);
    });
    $$('.v104-search-filters [data-v104-filter]').forEach(button => button.addEventListener('click', () => {
      state.filter = button.dataset.v104Filter || '';
      $$('.v104-search-filters button').forEach(item => item.classList.toggle('active', item === button));
      renderResults();
    }));
    elements.results?.addEventListener('click', handleResult);
    $$('[data-v104-setting]').forEach(group => group.addEventListener('click', event => {
      const button = event.target.closest('[data-value]');
      if (!button) return;
      const setting = group.dataset.v104Setting;
      const value = button.dataset.value;
      if (setting === 'density') document.documentElement.dataset.density = value;
      if (setting === 'font') document.documentElement.dataset.fontSize = value;
      store.set(keys[setting], value);
      activateSetting(setting, value);
    }));
    elements.split?.addEventListener('click', toggleSplit);
    elements.canvasClose?.addEventListener('click', () => {
      if (!state.split) return;
      state.split = false;
      document.body.classList.remove('v104-split-canvas');
      elements.split?.classList.remove('active');
      store.set(keys.split, 'false');
    });
    elements.messages?.addEventListener('click', event => {
      const button = event.target.closest('[data-v104-continue]');
      if (!button || window.JARVIS_APP.busy) return;
      const messages = window.JARVIS_APP.messages || [];
      const prior = [...messages].reverse().find(item => item.role === 'user');
      window.JARVIS_APP.setPrompt(`Continúa y completa la tarea anterior desde el último punto válido. Solicitud original: ${prior?.content || ''}`);
      window.JARVIS_APP.sendMessage();
    });
    document.addEventListener('click', event => {
      const button = event.target.closest('[data-memory-explain]');
      if (!button) return;
      explainMemory({ id: button.dataset.memoryExplain });
    });
    document.addEventListener('keydown', event => {
      if ((event.ctrlKey || event.metaKey) && event.shiftKey && event.key.toLowerCase() === 'k') {
        event.preventDefault(); openSearch();
      }
      if (event.key === 'Escape' && elements.dialog?.open) closeSearch();
    });
    matchMedia('(max-width: 1180px)').addEventListener?.('change', event => {
      if (event.matches && state.split) elements.canvasClose?.click();
    });
  }

  function cycleSidebar() {
    const sequence = ['full', 'compact', 'hidden'];
    state.sidebar = sequence[(sequence.indexOf(state.sidebar) + 1) % sequence.length];
    store.set(keys.sidebar, state.sidebar);
    applySidebar();
    window.JARVIS_APP.toast(`Panel lateral: ${state.sidebar === 'full' ? 'completo' : state.sidebar === 'compact' ? 'compacto' : 'oculto'}`);
  }

  function applySidebar() {
    document.body.classList.toggle('v104-sidebar-compact', state.sidebar === 'compact');
    document.body.classList.toggle('v104-sidebar-hidden', state.sidebar === 'hidden');
    elements.sidebar?.setAttribute('aria-label', `Panel lateral ${state.sidebar}. Pulsa para cambiar.`);
  }

  function activateSetting(setting, value) {
    $$(`[data-v104-setting="${setting}"] [data-value]`).forEach(button => button.classList.toggle('active', button.dataset.value === value));
  }

  function openSearch() {
    if (!elements.dialog?.open) elements.dialog?.showModal();
    setTimeout(() => elements.input?.focus(), 30);
  }
  function closeSearch() { if (elements.dialog?.open) elements.dialog.close(); }

  async function search() {
    const query = elements.input?.value.trim() || '';
    state.lastQuery = query;
    if (query.length < 2) { state.results = []; renderResults(); return; }
    elements.results.innerHTML = '<div class="v104-search-empty">Buscando en tu espacio…</div>';
    try {
      const sid = encodeURIComponent(window.JARVIS_APP.backendSessionId());
      const payload = await window.JARVIS_APP.request(`/api/v104/search?session_id=${sid}&q=${encodeURIComponent(query)}&project_name=&limit=40`, {}, { timeoutMs: 20000, attempts: 1 });
      if (query !== state.lastQuery) return;
      state.results = payload.results || [];
      renderResults();
    } catch (error) {
      elements.results.innerHTML = `<div class="v104-search-empty">${escapeHTML(error?.message || 'No fue posible buscar ahora.')}</div>`;
    }
  }

  function renderResults() {
    const visible = state.filter ? state.results.filter(item => item.type === state.filter) : state.results;
    if (!state.lastQuery || state.lastQuery.length < 2) {
      elements.results.innerHTML = '<div class="v104-search-empty">Escribe para encontrar información de tu espacio de trabajo.</div>';
      return;
    }
    if (!visible.length) {
      elements.results.innerHTML = '<div class="v104-search-empty">No se encontraron coincidencias en este filtro.</div>';
      return;
    }
    elements.results.innerHTML = visible.map((item, index) => `
      <button class="v104-search-result" type="button" data-result-index="${state.results.indexOf(item)}">
        <span class="v104-result-icon"><svg class="icon"><use href="#${iconFor(item.type)}"></use></svg></span>
        <span class="v104-result-copy"><strong>${escapeHTML(item.title || labelFor(item.type))}</strong><small>${escapeHTML(item.snippet || '')}</small></span>
        <span class="v104-result-type">${escapeHTML(labelFor(item.type))}</span>
      </button>`).join('');
  }

  async function handleResult(event) {
    const button = event.target.closest('[data-result-index]');
    if (!button) return;
    const item = state.results[Number(button.dataset.resultIndex)];
    if (!item) return;
    if (item.type === 'project') {
      const option = [...(elements.project?.options || [])].find(entry => entry.value === item.project_name);
      if (option) { elements.project.value = option.value; elements.project.dispatchEvent(new Event('change', { bubbles: true })); }
      closeSearch();
      window.JARVIS_APP.toast(`Proyecto ${item.project_name} activado`);
      return;
    }
    closeSearch();
    if (item.type === 'artifact') {
      $('#v100WorkspaceBtn')?.click();
      window.JARVIS_APP.toast(`Canvas abierto: ${item.title}`);
    } else {
      window.JARVIS_APP.openView('knowledge');
      if (item.type === 'memory') explainMemory(item);
    }
  }

  async function explainMemory(item) {
    try {
      const sid = encodeURIComponent(window.JARVIS_APP.backendSessionId());
      const response = await window.JARVIS_APP.request(`/api/v104/memory/${encodeURIComponent(item.id)}/explain?session_id=${sid}&q=${encodeURIComponent(state.lastQuery)}`, {}, { attempts: 1, timeoutMs: 12000 });
      const reason = response.explanation?.reasons?.join('; ');
      if (reason) window.JARVIS_APP.toast(`Memoria usada porque ${reason}.`);
    } catch { window.JARVIS_APP.toast('La memoria pertenece a tu sesión, pero su explicación detallada no está disponible.'); }
  }

  function toggleSplit() {
    if (!matchMedia('(min-width: 1181px)').matches) {
      $('#v100WorkspaceBtn')?.click();
      window.JARVIS_APP.toast('Canvas abierto como panel en esta pantalla.');
      return;
    }
    state.split = !state.split;
    store.set(keys.split, String(state.split));
    document.body.classList.toggle('v104-split-canvas', state.split);
    elements.split?.classList.toggle('active', state.split);
    if (state.split && !document.body.classList.contains('v100-workspace-open')) $('#v100WorkspaceBtn')?.click();
  }

  function observeProgress() {
    if (!elements.thinkingDetail || !elements.progress) return;
    const update = () => {
      const text = elements.thinkingDetail.textContent.toLowerCase();
      const phase = /verific|consolid|final/.test(text) ? 3 : /ejecut|herramient|fuente|recuper/.test(text) ? 2 : /plan|ruta|seleccion/.test(text) ? 1 : 0;
      $$('i', elements.progress).forEach((item, index) => {
        item.classList.toggle('done', index < phase);
        item.classList.toggle('active', index === phase);
      });
    };
    new MutationObserver(update).observe(elements.thinkingDetail, { childList: true, characterData: true, subtree: true });
    update();
  }

  function observeRecovery() {
    if (!elements.messages) return;
    const enhance = () => $$('.message-body.message-error', elements.messages).forEach(body => {
      if (body.querySelector('[data-v104-continue]')) return;
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'v104-recovery-action';
      button.dataset.v104Continue = 'true';
      button.textContent = 'Continuar desde el último punto';
      body.appendChild(button);
    });
    new MutationObserver(enhance).observe(elements.messages, { childList: true, subtree: true });
    enhance();
  }

  async function verifyContract() {
    try {
      const sid = encodeURIComponent(window.JARVIS_APP.backendSessionId());
      await window.JARVIS_APP.request(`/api/v104/status?session_id=${sid}`, {}, { attempts: 1, timeoutMs: 15000 });
      document.documentElement.dataset.v104 = 'ready';
    } catch { document.documentElement.dataset.v104 = 'degraded'; }
  }

  function iconFor(type) { return type === 'memory' ? 'i-knowledge' : type === 'document' ? 'i-file' : type === 'artifact' ? 'i-canvas' : 'i-target'; }
  function labelFor(type) { return ({ memory: 'Memoria', document: 'Archivo', artifact: 'Canvas', project: 'Proyecto' })[type] || 'Resultado'; }
  function escapeHTML(value) { return String(value || '').replace(/[&<>'"]/g, char => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', "'":'&#39;', '"':'&quot;' })[char]); }
})();
