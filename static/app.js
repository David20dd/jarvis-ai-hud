(() => {
  'use strict';

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const safeStorage = storage => ({
    getItem(key) { try { return storage?.getItem(key); } catch { return null; } },
    setItem(key, value) { try { storage?.setItem(key, value); } catch {} },
    removeItem(key) { try { storage?.removeItem(key); } catch {} }
  });
  const local = safeStorage(window.localStorage);
  const session = safeStorage(window.sessionStorage);

  const KEYS = {
    client: 'jarvis_v56_client',
    chats: 'jarvis_v56_chats',
    active: 'jarvis_v56_active_chat',
    api: 'jarvis_v56_api_base',
    token: 'jarvis_v56_auth_token',
    user: 'jarvis_v56_auth_user',
    mode: 'jarvis_v56_mode'
  };
  const LEGACY_KEYS = {
    client:'jarvis_v55_client', chats:'jarvis_v55_chats', active:'jarvis_v55_active_chat',
    api:'jarvis_v55_api_base', token:'jarvis_v55_auth_token', user:'jarvis_v55_auth_user', mode:'jarvis_v55_mode'
  };
  Object.keys(KEYS).forEach(name => {
    const target = name === 'token' || name === 'user' ? session : local;
    if (!target.getItem(KEYS[name])) {
      const legacy = target.getItem(LEGACY_KEYS[name]);
      if (legacy) target.setItem(KEYS[name], legacy);
    }
  });

  const els = {
    app: $('#app'), sidebar: $('#sidebar'), scrim: $('#scrim'), sidebarClose: $('#sidebarClose'),
    menuBtn: $('#menuBtn'), brandBtn: $('#brandBtn'), newChatBtn: $('#newChatBtn'), mobileNewBtn: $('#mobileNewBtn'),
    mobileCompose: $('#mobileCompose'), chatList: $('#chatList'), chatSearch: $('#chatSearch'), searchChatsBtn: $('#searchChatsBtn'), historyCount: $('#historyCount'),
    chatContextMenu: $('#chatContextMenu'), chatPinLabel: $('#chatPinLabel'),
    modeSelect: $('#modeSelect'), statusButton: $('#statusButton'), statusText: $('#statusText'), diagnosticsBtn: $('#diagnosticsBtn'),
    contextTitle: $('#contextTitle'), contextSubtitle: $('#contextSubtitle'), coreBanner: $('#coreBanner'), coreBannerText: $('#coreBannerText'), coreRetryBtn: $('#coreRetryBtn'),
    chatView: $('#chatView'), panelView: $('#panelView'), conversation: $('#conversation'), welcome: $('#welcome'), messages: $('#messages'),
    thinking: $('#thinking'), thinkingTitle: $('#thinkingTitle'), thinkingDetail: $('#thinkingDetail'),
    composer: $('#composer'), messageInput: $('#messageInput'), sendBtn: $('#sendBtn'), attachBtn: $('#attachBtn'),
    fileInput: $('#fileInput'), attachments: $('#attachments'), voiceBtn: $('#voiceBtn'),
    panelBack: $('#panelBack'), panelEyebrow: $('#panelEyebrow'), panelTitle: $('#panelTitle'), panelContent: $('#panelContent'), panelRefresh: $('#panelRefresh'),
    accountBtn: $('#accountBtn'), accountName: $('#accountName'), accountState: $('#accountState'), avatar: $('#avatar'),
    authModal: $('#authModal'), authForm: $('#authForm'), authTitle: $('#authTitle'), authCopy: $('#authCopy'), registerTab: $('#registerTab'),
    nameField: $('#nameField'), authName: $('#authName'), authEmail: $('#authEmail'), authPassword: $('#authPassword'), authError: $('#authError'), authSubmit: $('#authSubmit'),
    connectionModal: $('#connectionModal'), connectionExplanation: $('#connectionExplanation'), apiBaseInput: $('#apiBaseInput'),
    resetConnection: $('#resetConnection'), saveConnection: $('#saveConnection'), connectionResult: $('#connectionResult'), toast: $('#toast')
  };

  const isGitHubPages = location.hostname.endsWith('.github.io');
  const configuredBase = normalizeBase(window.JARVIS_CONFIG?.API_BASE || 'https://jarvis-ai-hud.onrender.com');
  const savedBase = normalizeBase(local.getItem(KEYS.api) || '');

  const state = {
    clientId: local.getItem(KEYS.client) || uid('client'),
    apiBase: isGitHubPages ? (savedBase || configuredBase) : savedBase,
    token: session.getItem(KEYS.token) || '',
    user: parseJSON(session.getItem(KEYS.user), null),
    auth: { required: false, registration: false, authenticated: false },
    core: { online: false, version: '', busy: false },
    mode: local.getItem(KEYS.mode) || 'auto',
    chats: parseJSON(local.getItem(KEYS.chats), {}),
    activeChatId: local.getItem(KEYS.active) || '',
    files: [],
    abortController: null,
    currentView: 'chat',
    authMode: 'login',
    toastTimer: null,
    phaseTimer: null,
    chatMenuTarget: '',
    chatMenuTrigger: null
  };
  local.setItem(KEYS.client, state.clientId);

  class ApiError extends Error {
    constructor(message, status = 0, data = null) {
      super(message);
      this.name = 'ApiError';
      this.status = Number(status || 0);
      this.data = data;
    }
  }

  document.addEventListener('DOMContentLoaded', init);

  function init() {
    ensureChat();
    bindEvents();
    els.modeSelect.value = state.mode;
    renderChatList();
    renderConversation();
    renderAttachments();
    autoResize();
    bootCore();
    registerServiceWorker();
  }

  function bindEvents() {
    els.menuBtn.addEventListener('click', () => els.app.classList.add('sidebar-open'));
    els.sidebarClose.addEventListener('click', closeSidebar);
    els.scrim.addEventListener('click', closeSidebar);
    els.brandBtn.addEventListener('click', () => openView('chat'));
    els.newChatBtn.addEventListener('click', newChat);
    els.mobileNewBtn.addEventListener('click', newChat);
    els.mobileCompose.addEventListener('click', newChat);
    els.panelBack.addEventListener('click', () => openView('chat'));
    els.panelRefresh.addEventListener('click', () => renderPanel(state.currentView));
    els.statusButton.addEventListener('click', () => state.core.online ? openView('system') : openConnection());
    els.diagnosticsBtn.addEventListener('click', () => openView('system'));
    els.accountBtn.addEventListener('click', openAccount);
    els.searchChatsBtn.addEventListener('click', () => {
      els.chatSearch.value = '';
      els.chatSearch.closest('.sidebar-search')?.classList.remove('has-query');
      renderChatList();
      els.chatSearch.focus();
    });
    els.chatSearch.addEventListener('input', () => {
      els.chatSearch.closest('.sidebar-search')?.classList.toggle('has-query', Boolean(els.chatSearch.value));
      renderChatList();
    });
    els.modeSelect.addEventListener('change', () => {
      state.mode = els.modeSelect.value;
      local.setItem(KEYS.mode, state.mode);
      renderConversation();
    });
    els.composer.addEventListener('submit', event => { event.preventDefault(); state.core.busy ? stopGeneration() : sendMessage(); });
    els.messageInput.addEventListener('input', autoResize);
    els.messageInput.addEventListener('keydown', event => {
      if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); state.core.busy ? stopGeneration() : sendMessage(); }
    });
    els.attachBtn.addEventListener('click', () => els.fileInput.click());
    els.fileInput.addEventListener('change', handleFiles);
    els.voiceBtn.addEventListener('click', startVoiceInput);
    els.chatContextMenu.addEventListener('click', event => {
      const actionButton = event.target.closest('[data-chat-action]');
      if (!actionButton || !state.chatMenuTarget) return;
      const target = state.chatMenuTarget;
      closeChatMenu();
      handleChatAction(actionButton.dataset.chatAction, target);
    });
    els.chatList.addEventListener('scroll', () => closeChatMenu(), { passive:true });
    els.messages.addEventListener('click', handleMessageAction);
    els.coreRetryBtn.addEventListener('click', async () => {
      els.coreRetryBtn.disabled = true;
      els.coreRetryBtn.textContent = 'Conectando…';
      const ok = await bootCore();
      els.coreRetryBtn.disabled = false;
      els.coreRetryBtn.textContent = ok ? 'Conectado' : 'Reintentar';
      if (ok) setTimeout(() => { els.coreRetryBtn.textContent = 'Reintentar'; }, 800);
    });
    $$('[data-prompt]').forEach(button => button.addEventListener('click', () => {
      els.messageInput.value = button.dataset.prompt || '';
      autoResize();
      els.messageInput.focus();
    }));
    $$('[data-view]').forEach(button => button.addEventListener('click', () => openView(button.dataset.view)));

    $$('[data-auth-tab]').forEach(button => button.addEventListener('click', () => setAuthMode(button.dataset.authTab)));
    els.authForm.addEventListener('submit', submitAuth);
    els.saveConnection.addEventListener('click', saveConnection);
    els.resetConnection.addEventListener('click', () => {
      state.apiBase = isGitHubPages ? configuredBase : '';
      local.removeItem(KEYS.api);
      els.apiBaseInput.value = state.apiBase || location.origin;
      testConnection();
    });

    window.addEventListener('online', bootCore);
    window.addEventListener('offline', () => setStatus('Sin conexión a internet', 'offline'));
    window.addEventListener('resize', () => closeChatMenu());
    document.addEventListener('keydown', event => { if (event.key === 'Escape') closeChatMenu(true); });
    document.addEventListener('click', event => {
      if (!event.target.closest('[data-chat-menu],#chatContextMenu')) closeChatMenu();
    });
  }

  function icon(name) {
    return `<svg class="icon" aria-hidden="true"><use href="#i-${name}"></use></svg>`;
  }

  function normalizeBase(value) {
    return String(value || '').trim().replace(/\/+$/, '').replace(/\/api\/jarvis(?:\/stream)?$/i, '');
  }

  function apiUrl(path) {
    const clean = path.startsWith('/') ? path : `/${path}`;
    return state.apiBase ? `${state.apiBase}${clean}` : clean;
  }

  function uid(prefix) {
    const random = window.crypto?.randomUUID?.() || `${Date.now()}_${Math.random().toString(36).slice(2)}`;
    return `${prefix}_${random}`;
  }

  function parseJSON(value, fallback) {
    try { return value ? JSON.parse(value) : fallback; } catch { return fallback; }
  }

  function escapeHTML(value) {
    return String(value ?? '').replace(/[&<>'"]/g, char => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', "'":'&#39;', '"':'&quot;' }[char]));
  }

  async function request(path, options = {}, config = {}) {
    const attempts = Math.max(1, Number(config.attempts || 1));
    const timeoutMs = Math.max(3000, Number(config.timeoutMs || 20000));
    const retryable = new Set([408, 425, 429, 500, 502, 503, 504]);
    let lastError;
    for (let attempt = 1; attempt <= attempts; attempt++) {
      const controller = new AbortController();
      const outerSignal = options.signal;
      const forwardAbort = () => controller.abort();
      if (outerSignal) {
        if (outerSignal.aborted) throw new DOMException('Solicitud cancelada', 'AbortError');
        outerSignal.addEventListener('abort', forwardAbort, { once: true });
      }
      const timer = setTimeout(() => controller.abort('timeout'), timeoutMs);
      try {
        const headers = new Headers(options.headers || {});
        if (state.token) headers.set('Authorization', `Bearer ${state.token}`);
        if (options.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
        const response = await fetch(apiUrl(path), { ...options, headers, signal: controller.signal, credentials: 'omit' });
        clearTimeout(timer);
        outerSignal?.removeEventListener('abort', forwardAbort);
        const raw = await response.text();
        let data = {};
        try { data = raw ? JSON.parse(raw) : {}; }
        catch { throw new ApiError(`El servidor respondió contenido no válido (HTTP ${response.status}).`, response.status); }
        if (response.ok) return data;
        const message = data.detail || data.reply || `Error HTTP ${response.status}`;
        const error = new ApiError(message, response.status, data);
        if (!retryable.has(response.status) || attempt === attempts) throw error;
        lastError = error;
      } catch (error) {
        clearTimeout(timer);
        outerSignal?.removeEventListener('abort', forwardAbort);
        if (outerSignal?.aborted) throw new DOMException('Solicitud cancelada', 'AbortError');
        if (error instanceof ApiError && (!retryable.has(error.status) || attempt === attempts)) throw error;
        lastError = error?.name === 'AbortError' ? new ApiError('El núcleo tardó demasiado en responder.', 0) : error;
        if (attempt === attempts) throw lastError;
      }
      await sleep(Math.min(800 * attempt, 1800));
    }
    throw lastError || new ApiError('No fue posible conectar con el núcleo.');
  }

  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

  async function bootCore() {
    setStatus('Conectando…', 'checking');
    try {
      const health = await request('/api/health/live', {}, { attempts: 2, timeoutMs: 15000 });
      state.core.online = health.status === 'ok';
      state.core.version = health.version || '';
      const auth = await request('/api/auth/status', {}, { attempts: 1, timeoutMs: 12000 });
      state.auth = {
        required: Boolean(auth.auth_required),
        registration: Boolean(auth.registration_enabled),
        authenticated: Boolean(auth.authenticated)
      };
      state.user = auth.user || null;
      if (!state.auth.authenticated && state.token) clearSession();
      if (state.auth.authenticated && state.user) saveUser();
      updateAccountUI();
      setStatus(state.auth.required && !state.auth.authenticated ? 'Inicia sesión' : 'Núcleo operativo', state.auth.required && !state.auth.authenticated ? 'checking' : 'online');
      if (state.auth.required && !state.auth.authenticated) openAccount(true);
      else startNotificationPolling();
      return true;
    } catch (error) {
      state.core.online = false;
      setStatus('Núcleo sin conexión', 'error');
      els.connectionExplanation.textContent = explainError(error);
      return false;
    }
  }

  function setStatus(text, type = 'checking') {
    els.statusText.textContent = text;
    els.statusButton.className = `status-button ${type}`;
    const unavailable = ['offline','error'].includes(type);
    els.coreBanner.hidden = !unavailable;
    if (unavailable) els.coreBannerText.textContent = text === 'Sin conexión a internet' ? 'Comprueba la red del dispositivo y vuelve a intentarlo.' : 'El chat conserva tu mensaje. Reintenta o revisa la conexión del núcleo.';
  }

  function explainError(error) {
    if (!navigator.onLine) return 'El dispositivo no tiene conexión a internet.';
    if (error?.status === 401) return 'El núcleo requiere iniciar sesión.';
    if (error?.status === 403) return 'El dominio o la cuenta no tienen autorización.';
    if (error?.status === 404) return 'La URL no corresponde al backend de JARVIS.';
    if ([502,503,504].includes(error?.status)) return 'Render está iniciando o el servicio no pudo arrancar.';
    return String(error?.message || 'No fue posible contactar el backend.').slice(0, 220);
  }

  function ensureChat() {
    if (state.activeChatId && state.chats[state.activeChatId]) return;
    const id = uid('chat');
    state.chats[id] = { id, title: 'Nueva conversación', messages: [], updatedAt: Date.now() };
    state.activeChatId = id;
    persistChats();
  }

  function currentChat() { ensureChat(); return state.chats[state.activeChatId]; }

  function persistChats() {
    local.setItem(KEYS.chats, JSON.stringify(state.chats));
    local.setItem(KEYS.active, state.activeChatId);
  }

  function newChat() {
    const id = uid('chat');
    state.chats[id] = { id, title: 'Nueva conversación', messages: [], updatedAt: Date.now() };
    state.activeChatId = id;
    state.files = [];
    persistChats();
    renderChatList();
    renderConversation();
    renderAttachments();
    openView('chat');
    els.messageInput.focus();
  }

  function renderChatList() {
    closeChatMenu();
    const query = els.chatSearch.value.trim().toLowerCase();
    const chats = Object.values(state.chats)
      .sort((a,b) => Number(Boolean(b.pinned)) - Number(Boolean(a.pinned)) || b.updatedAt - a.updatedAt)
      .filter(chat => {
        const searchable = `${chat.title} ${(chat.messages || []).slice(-3).map(item => item.content).join(' ')}`.toLowerCase();
        return !query || searchable.includes(query);
      });
    els.historyCount.textContent = String(chats.length);
    const groups = [];
    chats.forEach(chat => {
      const label = chat.pinned ? 'Fijadas' : chatDateGroup(chat.updatedAt);
      let group = groups.find(item => item.label === label);
      if (!group) { group = { label, chats:[] }; groups.push(group); }
      group.chats.push(chat);
    });
    els.chatList.innerHTML = groups.length ? groups.map(group => `
      <section class="chat-group" aria-label="${escapeHTML(group.label)}">
        <div class="chat-group-label">${escapeHTML(group.label)}</div>
        ${group.chats.map(chat => {
          const last = [...(chat.messages || [])].reverse().find(item => item.content)?.content || 'Sin mensajes todavía';
          return `<article class="chat-item ${chat.id === state.activeChatId ? 'active' : ''}" data-chat-id="${escapeHTML(chat.id)}" tabindex="0" aria-label="Abrir ${escapeHTML(chat.title)}">
            <div><strong>${chat.pinned ? '<span class="pin-mark">•</span>' : ''}${escapeHTML(chat.title)}</strong><span class="chat-preview">${escapeHTML(String(last).replace(/\s+/g,' ').slice(0,72))}</span><small>${relativeTime(chat.updatedAt)} · ${(chat.messages || []).length} mensajes</small></div>
            <button class="chat-more" data-chat-menu="${escapeHTML(chat.id)}" aria-label="Opciones de conversación" aria-haspopup="menu" aria-expanded="false">${icon('more')}</button>
          </article>`;
        }).join('')}
      </section>`).join('') : '<div class="empty-history">No encontramos conversaciones.</div>';
    $$('[data-chat-id]', els.chatList).forEach(item => {
      const open = event => {
        if (event.type === 'keydown' && !['Enter',' '].includes(event.key)) return;
        if (event.target.closest('[data-chat-menu],[data-chat-action]')) return;
        if (event.type === 'keydown') event.preventDefault();
        state.activeChatId = item.dataset.chatId;
        persistChats(); renderChatList(); renderConversation(); openView('chat');
      };
      item.addEventListener('click', open);
      item.addEventListener('keydown', open);
    });
    $$('[data-chat-menu]', els.chatList).forEach(button => button.addEventListener('click', event => {
      event.stopPropagation();
      toggleChatMenu(button, button.dataset.chatMenu);
    }));
  }

  function toggleChatMenu(trigger, chatId) {
    if (!trigger || !chatId) return;
    const isSameOpen = !els.chatContextMenu.hidden && state.chatMenuTarget === chatId;
    closeChatMenu();
    if (isSameOpen) return;

    const chat = state.chats[chatId];
    if (!chat) return;
    state.chatMenuTarget = chatId;
    state.chatMenuTrigger = trigger;
    els.chatPinLabel.textContent = chat.pinned ? 'Desfijar' : 'Fijar';
    trigger.setAttribute('aria-expanded', 'true');

    const menu = els.chatContextMenu;
    menu.hidden = false;
    menu.style.visibility = 'hidden';
    menu.classList.remove('is-open');

    const triggerRect = trigger.getBoundingClientRect();
    const sidebarRect = els.sidebar.getBoundingClientRect();
    const safe = 8;
    const menuWidth = menu.offsetWidth;
    const menuHeight = menu.offsetHeight;
    const minLeft = Math.max(safe, sidebarRect.left + safe);
    const maxLeft = Math.max(minLeft, Math.min(window.innerWidth - menuWidth - safe, sidebarRect.right - menuWidth - safe));
    const left = Math.min(Math.max(triggerRect.right - menuWidth, minLeft), maxLeft);
    let top = triggerRect.bottom + 7;
    if (top + menuHeight > window.innerHeight - safe) top = triggerRect.top - menuHeight - 7;
    top = Math.max(safe, Math.min(top, window.innerHeight - menuHeight - safe));

    menu.style.left = `${Math.round(left)}px`;
    menu.style.top = `${Math.round(top)}px`;
    menu.style.visibility = '';
    requestAnimationFrame(() => menu.classList.add('is-open'));
    menu.querySelector('[role="menuitem"]')?.focus({ preventScroll:true });
  }

  function closeChatMenu(restoreFocus = false) {
    const menu = els.chatContextMenu;
    if (!menu) return;
    const trigger = state.chatMenuTrigger;
    trigger?.setAttribute('aria-expanded', 'false');
    menu.classList.remove('is-open');
    menu.hidden = true;
    menu.style.removeProperty('left');
    menu.style.removeProperty('top');
    menu.style.removeProperty('visibility');
    state.chatMenuTarget = '';
    state.chatMenuTrigger = null;
    if (restoreFocus && trigger?.isConnected) trigger.focus({ preventScroll:true });
  }

  function chatDateGroup(timestamp) {
    const date = new Date(Number(timestamp || 0));
    const today = new Date();
    const startToday = new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime();
    const startDate = new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
    const days = Math.floor((startToday - startDate) / 86400000);
    if (days <= 0) return 'Hoy';
    if (days === 1) return 'Ayer';
    if (days <= 7) return 'Últimos 7 días';
    return 'Anteriores';
  }

  function handleChatAction(action, id) {
    const chat = state.chats[id];
    if (!chat) return;
    if (action === 'pin') chat.pinned = !chat.pinned;
    if (action === 'rename') {
      const title = prompt('Nuevo nombre de la conversación', chat.title);
      if (!title?.trim()) return;
      chat.title = title.trim().slice(0,80);
    }
    if (action === 'export') {
      const lines = (chat.messages || []).map(item => `## ${item.role === 'user' ? 'Usuario' : 'JARVIS'}\n\n${item.content}`).join('\n\n');
      const blob = new Blob([`# ${chat.title}\n\n${lines}\n`], { type:'text/markdown;charset=utf-8' });
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = `${chat.title.replace(/[^a-z0-9áéíóúñ_-]+/gi,'_').slice(0,60) || 'conversacion'}.md`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(link.href), 1000);
      toast('Conversación exportada');
      return;
    }
    if (action === 'delete') {
      if (!confirm('¿Eliminar esta conversación? Esta acción no se puede deshacer.')) return;
      if (Object.keys(state.chats).length === 1) { delete state.chats[id]; return newChat(); }
      delete state.chats[id];
      if (state.activeChatId === id) state.activeChatId = Object.keys(state.chats)[0];
    }
    chat.updatedAt = Date.now();
    persistChats(); renderChatList(); renderConversation();
  }

  function relativeTime(timestamp) {
    const diff = Date.now() - Number(timestamp || 0);
    if (diff < 60000) return 'ahora';
    if (diff < 3600000) return `${Math.floor(diff/60000)} min`;
    if (diff < 86400000) return `${Math.floor(diff/3600000)} h`;
    return new Date(timestamp).toLocaleDateString('es-HN', { day:'numeric', month:'short' });
  }

  function renderConversation() {
    const chat = currentChat();
    els.welcome.hidden = chat.messages.length > 0;
    els.messages.innerHTML = chat.messages.map(renderMessageHTML).join('');
    els.contextTitle.textContent = chat.title || 'Nueva conversación';
    els.contextSubtitle.textContent = chat.messages.length ? `${chat.messages.length} mensajes · ${state.mode === 'auto' ? 'Modo automático' : state.mode}` : 'Chat general';
    scrollBottom(false);
  }

  function renderMessageHTML(message, index) {
    const role = message.role === 'user' ? 'user' : 'assistant';
    const meta = message.meta || {};
    const adaptive = meta.adaptive || {};
    const evidence = adaptive.evidence || {};
    const traceItems = [meta.model, meta.route, meta.complexity, meta.cached ? 'caché' : ''].filter(Boolean);
    const evidenceItems = [
      Number(evidence.memory_hits||0) ? `Memoria ${Number(evidence.memory_hits)}` : '',
      Number(evidence.document_hits||0) ? `Documentos ${Number(evidence.document_hits)}` : '',
      Number(evidence.web_sources||0) ? `Web ${Number(evidence.web_sources)}` : '',
      adaptive.web_required ? 'Actualidad verificada' : '',
      adaptive.quality?.passed === true ? 'Control aprobado' : ''
    ].filter(Boolean);
    const traceHTML = role === 'assistant' && (traceItems.length || evidenceItems.length) ? `<details class="message-trace"><summary>Criterio y evidencia</summary><div>${[...evidenceItems,...traceItems].map(value => `<span>${escapeHTML(value)}</span>`).join('')}</div></details>` : '';
    const actions = role === 'assistant' ? `<div class="message-actions"><button class="message-tool" data-copy-message="${index}" aria-label="Copiar respuesta" title="Copiar">${icon('copy')}<span>Copiar</span></button><button class="message-tool" data-speak-message="${index}" aria-label="Escuchar respuesta" title="Escuchar">${icon('volume')}<span>Escuchar</span></button><button class="message-tool" data-regenerate-message="${index}" aria-label="Regenerar respuesta" title="Regenerar">${icon('rotate')}<span>Regenerar</span></button></div>` : '';
    if (role === 'user') return `<article class="message user"><div class="message-body">${formatContent(message.content)}</div></article>`;
    return `<article class="message assistant"><span class="message-avatar">J</span><div class="message-body ${meta.error ? 'message-error' : ''}">${formatContent(message.content)}${traceHTML}${actions}</div></article>`;
  }

  function formatContent(value) {
    const source = escapeHTML(value || '');
    const placeholders = [];
    const fenced = source.replace(/```([\w-]*)\n([\s\S]*?)```/g, (_, lang, code) => {
      const token = `@@JARVIS_CODE_${placeholders.length}@@`;
      placeholders.push(`<pre><div class="code-head"><span>${escapeHTML(lang || 'código')}</span><button class="code-copy" type="button" data-copy-code>${icon('copy')}<span>Copiar</span></button></div><code data-language="${escapeHTML(lang)}">${code.trim()}</code></pre>`);
      return token;
    });
    let html = fenced.split(/\n{2,}/).map(raw => {
      const block = raw.trim();
      if (!block) return '';
      if (/^@@JARVIS_CODE_\d+@@$/.test(block)) return block;
      if (/^###\s+/.test(block)) return `<h3>${inlineMarkdown(block.replace(/^###\s+/,''))}</h3>`;
      if (/^##\s+/.test(block)) return `<h2>${inlineMarkdown(block.replace(/^##\s+/,''))}</h2>`;
      if (/^#\s+/.test(block)) return `<h1>${inlineMarkdown(block.replace(/^#\s+/,''))}</h1>`;
      const lines = block.split('\n');
      if (lines.every(line => /^[-*]\s+/.test(line))) return `<ul>${lines.map(line => `<li>${inlineMarkdown(line.replace(/^[-*]\s+/,''))}</li>`).join('')}</ul>`;
      if (lines.every(line => /^\d+[.)]\s+/.test(line))) return `<ol>${lines.map(line => `<li>${inlineMarkdown(line.replace(/^\d+[.)]\s+/,''))}</li>`).join('')}</ol>`;
      return `<p>${lines.map(inlineMarkdown).join('<br>')}</p>`;
    }).join('');
    placeholders.forEach((content,index) => { html = html.replace(`@@JARVIS_CODE_${index}@@`, content); });
    return html;
  }

  function inlineMarkdown(value) {
    return String(value || '')
      .replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>')
      .replace(/`([^`]+)`/g,'<code>$1</code>')
      .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,'<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
  }

  async function handleMessageAction(event) {
    const codeButton = event.target.closest('[data-copy-code]');
    if (codeButton) {
      await copyText(codeButton.closest('pre')?.querySelector('code')?.textContent || '');
      codeButton.querySelector('span').textContent = 'Copiado';
      setTimeout(() => { const label=codeButton.querySelector('span'); if(label)label.textContent='Copiar'; }, 1000);
      return;
    }
    const copyButton = event.target.closest('[data-copy-message]');
    if (copyButton) {
      const message = currentChat().messages[Number(copyButton.dataset.copyMessage)];
      await copyText(message?.content || '');
      toast('Respuesta copiada');
      return;
    }
    const speakButton = event.target.closest('[data-speak-message]');
    if (speakButton) { speakMessage(Number(speakButton.dataset.speakMessage), speakButton); return; }
    const regenerate = event.target.closest('[data-regenerate-message]');
    if (regenerate && !state.core.busy) {
      const index = Number(regenerate.dataset.regenerateMessage);
      const messages = currentChat().messages;
      const previous = [...messages.slice(0,index)].reverse().find(item => item.role === 'user');
      if (!previous) return;
      els.messageInput.value = previous.content;
      autoResize();
      await sendMessage();
    }
  }

  async function copyText(value) {
    const text = String(value || '');
    if (navigator.clipboard?.writeText) return navigator.clipboard.writeText(text);
    const area = document.createElement('textarea');
    area.value = text; area.style.position = 'fixed'; area.style.opacity = '0';
    document.body.appendChild(area); area.select(); document.execCommand('copy'); area.remove();
  }

  function addMessage(role, content, meta = {}) {
    const chat = currentChat();
    chat.messages.push({ role, content: String(content || ''), meta, createdAt: Date.now() });
    chat.updatedAt = Date.now();
    if (role === 'user' && chat.title === 'Nueva conversación') chat.title = String(content).replace(/\s+/g,' ').slice(0,46) || 'Conversación';
    persistChats();
    renderChatList();
    renderConversation();
  }

  async function sendMessage() {
    const text = els.messageInput.value.trim();
    if (!text && !state.files.length) return;
    const prompt = text || 'Analiza los archivos adjuntos.';
    const files = state.files.map(file => ({ file_name:file.name, file_b64:file.base64, mime_type:file.type || '' }));
    addMessage('user', prompt);
    els.messageInput.value = '';
    state.files = [];
    renderAttachments();
    autoResize();
    setBusy(true, 'Analizando la solicitud…');
    state.abortController = new AbortController();

    try {
      if (!state.core.online) {
        els.thinkingDetail.textContent = 'Conectando con el núcleo…';
        const connected = await bootCore();
        if (!connected) throw new ApiError('No fue posible conectar con el núcleo.', 0);
      }
      if (state.auth.required && !state.auth.authenticated) {
        addMessage('assistant', 'El núcleo está disponible, pero esta instalación requiere iniciar sesión. Abre **Cuenta personal** y vuelve a enviar el mensaje.', { error:true, route:'authentication' });
        openAccount(true);
        return;
      }
      const data = await request('/api/jarvis', {
        method:'POST',
        signal: state.abortController.signal,
        body:JSON.stringify({
          message:prompt,
          session_id:backendSessionId(),
          files,
          mode:state.mode,
          project_name:'General',
          request_id:uid('request')
        })
      }, { attempts:2, timeoutMs:65000 });
      const reply = String(data.reply || data.response || '').trim();
      if (!reply) throw new ApiError('El núcleo respondió sin contenido.');
      addMessage('assistant', reply, {
        model:data.model || '', route:data.route || data.mode || '', cached:Boolean(data.cached),
        complexity:data.intelligence?.complexity || '', adaptive:data.adaptive || {}
      });
      setStatus('Núcleo operativo', 'online');
    } catch (error) {
      if (error?.name === 'AbortError') addMessage('assistant', 'Generación detenida por el usuario.', { error:true, route:'cancelled' });
      else if (error?.status === 401) {
        clearSession();
        addMessage('assistant', '🔐 El núcleo está operativo, pero requiere iniciar sesión. Abre **Cuenta personal** y vuelve a intentarlo.', { error:true, route:'authentication' });
        openAccount(true);
      } else {
        const localReply = localRecovery(prompt, error);
        addMessage('assistant', localReply, { error:true, route:'local_recovery' });
        setStatus('Revisar conexión', 'error');
      }
    } finally {
      state.abortController = null;
      setBusy(false);
    }
  }

  function localRecovery(prompt, error) {
    const expression = String(prompt).trim().replace(/,/g,'.').replace(/×/g,'*').replace(/÷/g,'/');
    if (/^[\d\s()+\-*/.%]+$/.test(expression) && expression.length < 100) {
      try {
        const result = Function(`"use strict";return (${expression})`)();
        if (Number.isFinite(result)) return `Resultado local: **${result}**.\n\nEl cálculo se completó en el dispositivo mientras se revisa la conexión remota.`;
      } catch {}
    }
    return `⚠️ **JARVIS recibió tu mensaje, pero no pudo completar la solicitud remota.**\n\n${explainError(error)}\n\nNo se seguirá reintentando indefinidamente. Abre el indicador de estado para revisar la conexión y vuelve a enviar cuando aparezca **Núcleo operativo**.`;
  }

  function stopGeneration() { state.abortController?.abort(); }

  async function speakMessage(index, button) {
    const message=currentChat().messages[index];
    if(!message || message.role!=='assistant')return;
    const original=button.innerHTML;
    button.disabled=true;button.innerHTML=`${icon('volume')}<span>Preparando…</span>`;
    try{
      const headers=new Headers({'Content-Type':'application/json'});
      if(state.token)headers.set('Authorization',`Bearer ${state.token}`);
      const response=await fetch(apiUrl('/api/voice/speech'),{method:'POST',headers,body:JSON.stringify({text:String(message.content||'').slice(0,4000)})});
      if(!response.ok){let detail='Voz no disponible';try{detail=(await response.json()).detail||detail;}catch{}throw new Error(detail);}
      const url=URL.createObjectURL(await response.blob()),audio=new Audio(url);
      audio.onended=()=>URL.revokeObjectURL(url);await audio.play();button.innerHTML=`${icon('volume')}<span>Reproduciendo</span>`;
    }catch(error){toast(error.message||'No fue posible generar voz.');}
    finally{setTimeout(()=>{button.disabled=false;button.innerHTML=original;},900);}
  }

  function setBusy(busy, detail = '') {
    state.core.busy = busy;
    els.thinking.hidden = !busy;
    els.thinkingDetail.textContent = detail || 'Procesando…';
    els.sendBtn.classList.toggle('stop', busy);
    els.sendBtn.setAttribute('aria-label', busy ? 'Detener generación' : 'Enviar mensaje');
    els.sendBtn.innerHTML = busy ? icon('stop') : icon('send');
    clearInterval(state.phaseTimer);
    state.phaseTimer = null;
    if (busy) {
      const phases = ['Analizando la solicitud…','Preparando la mejor ruta…','Ejecutando herramientas necesarias…','Verificando el resultado…'];
      let index = 0;
      state.phaseTimer = setInterval(() => { index = Math.min(index + 1, phases.length - 1); els.thinkingDetail.textContent = phases[index]; }, 6500);
      scrollBottom();
    }
  }

  function backendSessionId() {
    const owner = state.user?.id || state.clientId;
    return `web:${owner}:${state.activeChatId}`.slice(0,150);
  }

  async function handleFiles(event) {
    const selected = [...event.target.files];
    event.target.value = '';
    for (const file of selected) {
      if (file.size > 12 * 1024 * 1024) { toast(`${file.name} supera 12 MB.`); continue; }
      try { state.files.push({ name:file.name, type:file.type || '', base64:await fileToBase64(file), size:file.size }); }
      catch { toast(`No se pudo leer ${file.name}.`); }
    }
    renderAttachments();
  }

  function fileToBase64(file) {
    return new Promise((resolve,reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result).split(',')[1] || '');
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
  }

  function renderAttachments() {
    els.attachments.hidden = !state.files.length;
    els.attachments.innerHTML = state.files.map((file,index) => `<div class="attachment-chip"><span>${escapeHTML(file.name)}</span><button data-remove-file="${index}" aria-label="Quitar archivo">×</button></div>`).join('');
    $$('[data-remove-file]', els.attachments).forEach(button => button.addEventListener('click', () => {
      state.files.splice(Number(button.dataset.removeFile),1); renderAttachments();
    }));
  }

  function autoResize() {
    els.messageInput.style.height = 'auto';
    els.messageInput.style.height = `${Math.min(180, Math.max(42, els.messageInput.scrollHeight))}px`;
  }

  function scrollBottom(smooth = true) {
    requestAnimationFrame(() => els.conversation.scrollTo({ top:els.conversation.scrollHeight, behavior:smooth ? 'smooth' : 'auto' }));
  }

  function closeSidebar() { els.app.classList.remove('sidebar-open'); }

  function openView(view) {
    closeSidebar();
    state.currentView = view;
    $$('[data-view]').forEach(button => button.classList.toggle('active', button.dataset.view === view));
    if (view === 'chat') {
      els.chatView.classList.add('active');
      els.panelView.classList.remove('active');
      renderConversation();
      return;
    }
    if (state.auth.required && !state.auth.authenticated) { openAccount(true); return; }
    els.chatView.classList.remove('active');
    els.panelView.classList.add('active');
    renderPanel(view);
  }

  const PANEL_INFO = {
    knowledge:['CONOCIMIENTO','Biblioteca y memoria'], missions:['AUTONOMÍA','Misiones'],
    nexus:['CONTROL','Nexus v65'], channels:['TELEGRAM','Asistente móvil'],
    library:['CONOCIMIENTO','Biblioteca'], memory:['CONTEXTO','Memoria'], system:['ESTADO','Diagnóstico del núcleo']
  };

  async function renderPanel(view) {
    const [eyebrow,title] = PANEL_INFO[view] || ['JARVIS','Panel'];
    els.panelEyebrow.textContent = eyebrow;
    els.panelTitle.textContent = title;
    els.contextTitle.textContent = title;
    els.contextSubtitle.textContent = eyebrow;
    els.panelContent.innerHTML = '<div class="empty-state">Cargando…</div>';
    try {
      if (view === 'knowledge') await renderKnowledge();
      else if (view === 'nexus') await renderNexus();
      else if (view === 'library') await renderLibrary();
      else if (view === 'memory') await renderMemory();
      else if (view === 'missions') await renderMissions();
      else if (view === 'channels') await renderChannels();
      else await renderSystem();
    } catch (error) {
      if (error.status === 401) { clearSession(); openAccount(true); return; }
      els.panelContent.innerHTML = `<div class="empty-state">${escapeHTML(explainError(error))}<br><br><button class="soft-btn" id="retryPanel">Volver a intentar</button></div>`;
      $('#retryPanel')?.addEventListener('click', () => renderPanel(view));
    }
  }

  async function renderLibrary() {
    const data = await request(`/api/library?session_id=${encodeURIComponent(backendSessionId())}`);
    const docs = data.documents || [];
    els.panelContent.innerHTML = `
      <div class="panel-grid"><article class="panel-card"><h3>Archivos disponibles</h3><strong class="metric">${docs.length}</strong><p>Documentos vinculados al espacio actual.</p></article><article class="panel-card"><h3>Subida segura</h3><p>Máximo 12 MB por archivo. PDF, Word, Excel, PowerPoint, texto y código.</p><button class="primary-btn" id="libraryUploadBtn" style="margin-top:12px">Subir archivo</button><input id="libraryFileInput" type="file" hidden /></article></div>
      <section class="panel-section"><div class="panel-section-head"><h3>Documentos</h3></div><div class="list-stack">${docs.length ? docs.map(doc => `<article class="list-row"><div><strong>${escapeHTML(doc.file_name || doc.name || 'Documento')}</strong><small>${escapeHTML(doc.file_type || '')} · ${escapeHTML(String(doc.created_at || ''))}</small></div><button class="danger-btn" data-delete-doc="${escapeHTML(doc.id)}">Eliminar</button></article>`).join('') : '<div class="empty-state">Todavía no hay documentos.</div>'}</div></section>`;
    $('#libraryUploadBtn').addEventListener('click', () => $('#libraryFileInput').click());
    $('#libraryFileInput').addEventListener('change', async event => {
      const file = event.target.files[0]; if (!file) return;
      if (file.size > 12*1024*1024) return toast('El archivo supera 12 MB.');
      const button = $('#libraryUploadBtn'); button.disabled = true; button.textContent = 'Subiendo…';
      try {
        await request('/api/library/upload', { method:'POST', body:JSON.stringify({ session_id:backendSessionId(), file_name:file.name, file_b64:await fileToBase64(file) }) }, { timeoutMs:65000 });
        toast('Archivo guardado'); renderLibrary();
      } catch (error) { toast(explainError(error)); button.disabled = false; button.textContent = 'Subir archivo'; }
    });
    $$('[data-delete-doc]').forEach(button => button.addEventListener('click', async () => {
      if (!confirm('¿Eliminar este documento de JARVIS?')) return;
      await request(`/api/library/${encodeURIComponent(button.dataset.deleteDoc)}?session_id=${encodeURIComponent(backendSessionId())}`, { method:'DELETE' });
      renderLibrary();
    }));
  }

  async function renderMemory() {
    const data = await request(`/api/memory?session_id=${encodeURIComponent(backendSessionId())}`);
    const memories = data.memories || [];
    els.panelContent.innerHTML = `
      <div class="panel-card"><h3>Guardar un recuerdo</h3><p>Conserva únicamente preferencias o información útil que quieras reutilizar.</p><div class="form-grid" style="margin-top:13px"><input class="text-input" id="memoryContent" placeholder="Ejemplo: Prefiero respuestas breves"/><select class="text-input" id="memoryCategory"><option value="preference">Preferencia</option><option value="project">Proyecto</option><option value="fact">Dato</option></select><button class="primary-btn" id="saveMemory">Guardar</button></div></div>
      <section class="panel-section"><div class="panel-section-head"><h3>Recuerdos</h3><span class="status-tag">${memories.length}</span></div><div class="list-stack">${memories.length ? memories.map(item => `<article class="list-row"><div><strong>${escapeHTML(item.content)}</strong><small>${escapeHTML(item.category || 'memory')} · importancia ${Number(item.importance || 3)}</small></div><button class="danger-btn" data-delete-memory="${escapeHTML(item.id)}">Eliminar</button></article>`).join('') : '<div class="empty-state">JARVIS no ha guardado recuerdos todavía.</div>'}</div></section>`;
    $('#saveMemory').addEventListener('click', async () => {
      const content = $('#memoryContent').value.trim(); if (!content) return;
      await request('/api/memory', { method:'POST', body:JSON.stringify({ session_id:backendSessionId(), content, category:$('#memoryCategory').value, importance:3 }) });
      toast('Recuerdo guardado'); renderMemory();
    });
    $$('[data-delete-memory]').forEach(button => button.addEventListener('click', async () => {
      await request(`/api/memory/${encodeURIComponent(button.dataset.deleteMemory)}?session_id=${encodeURIComponent(backendSessionId())}`, { method:'DELETE' }); renderMemory();
    }));
  }

  async function renderKnowledge() {
    const sid = encodeURIComponent(backendSessionId());
    const results = await Promise.allSettled([
      request(`/api/library?session_id=${sid}`),
      request(`/api/memory?session_id=${sid}`),
      request(`/api/knowledge/facts?session_id=${sid}&limit=30`),
      request(`/api/research/library?session_id=${sid}&limit=8`)
    ]);
    const docs = valueOf(results[0]).documents || [];
    const memories = valueOf(results[1]).memories || [];
    const facts = valueOf(results[2]).facts || [];
    const research = valueOf(results[3]);
    const researchRuns = research.runs || [];
    const researchStatus = research.status || {};
    els.panelContent.innerHTML = `
      <div class="panel-grid knowledge-metrics">
        <article class="panel-card metric-card"><span class="card-kicker">ARCHIVOS</span><strong class="metric">${docs.length}</strong><p>Documentos del espacio actual.</p></article>
        <article class="panel-card metric-card"><span class="card-kicker">MEMORIA</span><strong class="metric">${memories.length}</strong><p>Preferencias y contexto personal.</p></article>
        <article class="panel-card metric-card"><span class="card-kicker">HECHOS</span><strong class="metric">${facts.length}</strong><p>Conocimiento estructurado y trazable.</p></article>
        <article class="panel-card metric-card"><span class="card-kicker">FUENTES WEB</span><strong class="metric">${Number(researchStatus.sources||0)}</strong><p>Evidencia recuperada e indexada.</p></article>
      </div>
      <section class="panel-section">
        <article class="panel-card research-workbench">
          <div class="panel-section-head"><div><span class="card-kicker">INVESTIGACIÓN CONTROLADA</span><h3>Buscar, leer e incorporar evidencia</h3></div><span class="status-tag ${researchStatus.sources?'ok':'warn'}">Google ${state.core?.google_search?.configured?'listo':'opcional'} · web abierta</span></div>
          <p>JARVIS consulta varias rutas, deduplica fuentes, lee páginas públicas seguras y las añade a la memoria semántica con procedencia.</p>
          <div class="research-controls"><input class="text-input" id="researchQuery" placeholder="Tema, pregunta o hecho que deseas investigar"/><select class="text-input" id="researchDepth"><option value="8">Rápida · 8 fuentes</option><option value="16" selected>Profunda · 16 fuentes</option><option value="24">Extensa · 24 fuentes</option></select><button class="primary-btn" id="runResearch">Investigar</button></div>
          <div class="research-result" id="researchResult" hidden></div>
        </article>
      </section>
      <section class="panel-section knowledge-actions">
        <article class="panel-card">
          <div class="panel-section-head"><div><span class="card-kicker">CAPTURAR</span><h3>Agregar conocimiento</h3></div></div>
          <div class="form-grid knowledge-form"><input class="text-input" id="factSubject" placeholder="Tema o entidad"/><input class="text-input" id="factObject" placeholder="Información que JARVIS debe conservar"/><button class="primary-btn" id="saveFact">Guardar hecho</button></div>
          <div class="button-row compact-row"><button class="soft-btn" id="saveQuickMemory">Guardar como preferencia</button><button class="soft-btn" id="knowledgeUploadBtn">Subir documento</button><input id="knowledgeFileInput" type="file" hidden /></div>
        </article>
      </section>
      <section class="panel-section"><div class="panel-section-head"><h3>Conocimiento reciente</h3><span class="status-tag">${docs.length + memories.length + facts.length}</span></div>
        <div class="knowledge-columns">
          <div><span class="column-label">HECHOS VERIFICABLES</span><div class="list-stack">${facts.length ? facts.map(item => `<article class="list-row"><div><strong>${escapeHTML(item.subject)} · ${escapeHTML(item.predicate)}</strong><small>${escapeHTML(item.object_text)} · confianza ${Math.round(Number(item.confidence||0)*100)}%</small></div><button class="danger-btn" data-delete-fact="${escapeHTML(item.id)}">Eliminar</button></article>`).join('') : '<div class="empty-state">Añade el primer hecho útil.</div>'}</div></div>
          <div><span class="column-label">MEMORIA Y ARCHIVOS</span><div class="list-stack">${[
            ...memories.slice(0,8).map(item => `<article class="list-row"><div><strong>${escapeHTML(item.content)}</strong><small>Memoria · ${escapeHTML(item.category||'contexto')}</small></div></article>`),
            ...docs.slice(0,8).map(item => `<article class="list-row"><div><strong>${escapeHTML(item.file_name||'Documento')}</strong><small>Archivo · ${escapeHTML(item.file_type||'')}</small></div></article>`)
          ].join('') || '<div class="empty-state">Todavía no hay memoria ni archivos.</div>'}</div></div>
        </div>
      </section>
      <section class="panel-section"><div class="panel-section-head"><h3>Investigaciones guardadas</h3><span class="status-tag">${researchRuns.length}</span></div><div class="list-stack">${researchRuns.length?researchRuns.map(item=>`<article class="list-row research-run"><div><strong>${escapeHTML(item.query)}</strong><small>${Number(item.source_count||0)} fuentes · ${Number(item.official_count||0)} prioritarias · ${(item.providers||[]).map(escapeHTML).join(' + ')||'web'}</small></div><span class="status-tag ${item.status==='completed'?'ok':'warn'}">${escapeHTML(item.status)}</span></article>`).join(''):'<div class="empty-state">Las investigaciones trazables aparecerán aquí.</div>'}</div></section>`;
    $('#runResearch')?.addEventListener('click', async () => {
      const query=$('#researchQuery').value.trim(); if(!query)return toast('Escribe un tema para investigar.');
      const button=$('#runResearch'), output=$('#researchResult'); button.disabled=true; button.textContent='Investigando…'; output.hidden=false; output.innerHTML='<div class="empty-state">Buscando, leyendo y verificando fuentes…</div>';
      try {
        const pack=await request('/api/research/ingest',{method:'POST',body:JSON.stringify({session_id:backendSessionId(),query,project_name:'General',max_sources:Number($('#researchDepth').value),fetch_pages:true,page_limit:4})},{attempts:1,timeoutMs:120000});
        const evidence=pack.evidence||[];
        output.innerHTML=`<div class="research-summary"><strong>${evidence.length} fuentes incorporadas</strong><span>${Number(pack.official_or_primary_count||0)} prioritarias · ${Number(pack.pages_fetched||0)} páginas leídas</span></div><div class="source-grid">${evidence.slice(0,8).map((item,index)=>`<a class="source-card" href="${escapeHTML(item.url||'#')}" target="_blank" rel="noopener noreferrer"><span>${String(index+1).padStart(2,'0')}</span><div><strong>${escapeHTML(item.title||'Fuente')}</strong><small>${escapeHTML(item.provider||'web')} · calidad ${Math.round(Number(item.quality||0)*100)}%</small></div></a>`).join('')}</div>`;
        toast('Investigación guardada en la memoria semántica');
      } catch(error) { output.innerHTML=`<div class="empty-state error-state">${escapeHTML(explainError(error))}</div>`; }
      finally { button.disabled=false; button.textContent='Investigar'; }
    });
    $('#saveFact')?.addEventListener('click', async () => {
      const subject=$('#factSubject').value.trim(), object_text=$('#factObject').value.trim();
      if (!subject || !object_text) return toast('Completa el tema y la información.');
      await request('/api/knowledge/facts', { method:'POST', body:JSON.stringify({ session_id:backendSessionId(), project_name:'General', subject, predicate:'relacionado con', object_text, confidence:.75, verified:false }) });
      toast('Conocimiento guardado'); renderKnowledge();
    });
    $('#saveQuickMemory')?.addEventListener('click', async () => {
      const content=$('#factObject').value.trim(); if (!content) return toast('Escribe primero la información.');
      await request('/api/memory', { method:'POST', body:JSON.stringify({ session_id:backendSessionId(), content, category:'preference', importance:3 }) });
      toast('Preferencia guardada'); renderKnowledge();
    });
    $('#knowledgeUploadBtn')?.addEventListener('click', () => $('#knowledgeFileInput').click());
    $('#knowledgeFileInput')?.addEventListener('change', async event => {
      const file=event.target.files[0]; if (!file) return;
      if (file.size > 12*1024*1024) return toast('El archivo supera 12 MB.');
      const button=$('#knowledgeUploadBtn'); button.disabled=true; button.textContent='Subiendo…';
      try {
        await request('/api/library/upload', { method:'POST', body:JSON.stringify({ session_id:backendSessionId(), file_name:file.name, file_b64:await fileToBase64(file) }) }, { timeoutMs:65000 });
        toast('Documento indexado'); renderKnowledge();
      } catch(error) { toast(explainError(error)); button.disabled=false; button.textContent='Subir documento'; }
    });
    $$('[data-delete-fact]').forEach(button => button.addEventListener('click', async () => {
      if (!confirm('¿Eliminar este hecho de JARVIS?')) return;
      await request(`/api/knowledge/facts/${encodeURIComponent(button.dataset.deleteFact)}?session_id=${sid}`, { method:'DELETE' });
      renderKnowledge();
    }));
  }

  function renderArtifactCard(item) {
    const spec=item.spec||{}, kind=String(item.artifact_type||'');
    let body='';
    if (kind==='chart') {
      const values=(spec.values||[]).map(Number), max=Math.max(1,...values.map(Math.abs));
      body=`<div class="mini-chart">${values.map((value,index)=>`<div><span>${escapeHTML((spec.labels||[])[index]||`Dato ${index+1}`)}</span><i style="width:${Math.max(2,Math.abs(value)/max*100)}%"></i><b>${escapeHTML(value)}${escapeHTML(spec.unit||'')}</b></div>`).join('')}</div>`;
    } else if (kind==='table' || kind==='comparison') {
      const columns=spec.columns||[], rows=spec.rows||[];
      body=`<div class="artifact-table"><table><thead><tr>${columns.map(value=>`<th>${escapeHTML(value)}</th>`).join('')}</tr></thead><tbody>${rows.map(row=>`<tr>${(Array.isArray(row)?row:columns.map(key=>row[key])).map(value=>`<td>${escapeHTML(value)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
    } else {
      body=`<ol class="artifact-list">${(spec.items||[]).map(value=>`<li>${escapeHTML(value)}</li>`).join('')}</ol>`;
    }
    return `<article class="panel-card artifact-card"><div class="panel-section-head"><div><span class="card-kicker">${escapeHTML(kind.toUpperCase())}</span><h3>${escapeHTML(item.title)}</h3></div></div>${body||'<p>Sin datos todavía.</p>'}</article>`;
  }

  async function renderNexus() {
    const sid=encodeURIComponent(backendSessionId());
    const results=await Promise.allSettled([
      request(`/api/v65/status?session_id=${sid}`), request('/api/integrations'),
      request(`/api/artifacts?session_id=${sid}&limit=12`), request(`/api/automations?session_id=${sid}&limit=12`),
      request(`/api/intelligence/decisions?session_id=${sid}&limit=8`),
      request(`/api/actions?session_id=${sid}&limit=20`), request(`/api/operations/v65?session_id=${sid}`),
      request(`/api/adaptive/status?session_id=${sid}&limit=8`)
    ]);
    const core=valueOf(results[0]), integrations=valueOf(results[1]).integrations||[], artifacts=valueOf(results[2]).artifacts||[];
    const automations=valueOf(results[3]).automations||[], decisions=valueOf(results[4]).decisions||[];
    const actions=valueOf(results[5]).actions||[], operations=valueOf(results[6]), adaptive=valueOf(results[7]);
    const providers=core.providers?.configured||[], intelligence=core.intelligence||{};
    const pendingActions=actions.filter(item=>item.status==='pending_approval');
    const latestQuality=operations.latest||{};
    els.panelContent.innerHTML=`
      <div class="nexus-hero panel-card"><div><span class="card-kicker">ADAPTIVE INTELLIGENCE · v66</span><h3>Inteligencia, evidencia y acción bajo tu control</h3><p>JARVIS decide cuándo consultar memoria, documentos o internet; verifica actualidad y mantiene las acciones sensibles bajo aprobación.</p></div><button class="soft-btn" id="nexusDiagnostics">Diagnóstico</button></div>
      <div class="panel-grid nexus-metrics">
        <article class="panel-card metric-card"><span class="card-kicker">PROVEEDORES</span><strong class="metric">${providers.length}</strong><p>${providers.length?providers.map(escapeHTML).join(' · '):'Modo local disponible'}</p></article>
        <article class="panel-card metric-card"><span class="card-kicker">DECISIONES</span><strong class="metric">${Object.values(intelligence.decisions||{}).reduce((a,b)=>a+Number(b||0),0)}</strong><p>Rutas registradas por el planificador.</p></article>
        <article class="panel-card metric-card"><span class="card-kicker">AUTOMATIZACIONES</span><strong class="metric">${automations.length}</strong><p>Rutinas persistentes del espacio.</p></article>
        <article class="panel-card metric-card"><span class="card-kicker">APROBACIONES</span><strong class="metric">${pendingActions.length}</strong><p>Acciones sensibles esperando tu decisión.</p></article>
      </div>
      <section class="panel-section"><div class="panel-section-head"><h3>Criterio adaptativo</h3><span class="status-tag ok">${adaptive.enabled===false?'Desactivado':'Activo'}</span></div><article class="panel-card adaptive-card"><div><span class="card-kicker">RESPUESTAS EVALUADAS</span><strong class="metric">${Number(adaptive.summary?.decisions||0)}</strong></div><div><strong>${Math.round(Number(adaptive.summary?.verification_rate||0)*100)}% verificadas</strong><p>${escapeHTML(adaptive.recommendations?.[0]?.detail||'JARVIS está aprendiendo qué rutas entregan mejores resultados sin modificar su código ni sus permisos.')}</p></div></article></section>
      <section class="panel-section"><article class="panel-card"><span class="card-kicker">PLANIFICADOR</span><h3>Diseña una ejecución antes de consumir recursos</h3><div class="form-grid nexus-planner"><input class="text-input" id="nexusObjective" placeholder="Objetivo concreto"/><select class="text-input" id="nexusMode"><option value="auto">Automático</option><option value="research">Investigación</option><option value="professional">Profesional</option><option value="private">Privado/local</option></select><button class="soft-btn" id="previewNexusPlan">Ver plan</button><button class="primary-btn" id="runNexusPlan">Ejecutar</button></div><div id="nexusPlanResult" class="plan-result" hidden></div></article></section>
      <section class="panel-section"><div class="panel-section-head"><h3>Centro de acciones</h3><span class="status-tag">aprobación obligatoria</span></div><article class="panel-card action-center"><p>Prepara una acción, revisa sus argumentos y autorízala antes de que JARVIS modifique datos o envíe algo fuera del núcleo.</p><div class="action-form"><select class="text-input" id="actionType"><option value="memory.save">Guardar memoria</option><option value="reminder.create">Crear recordatorio</option><option value="automation.create">Crear automatización</option><option value="telegram.notify">Enviar por Telegram</option></select><input class="text-input" id="actionTarget" placeholder="Título o destinatario"/><textarea class="text-input" id="actionContent" placeholder="Contenido o instrucciones"></textarea><input class="text-input" id="actionSchedule" placeholder="Fecha ISO o intervalo opcional"/><button class="primary-btn" id="prepareAction">Preparar</button></div></article><div class="list-stack action-list">${actions.length?actions.map(item=>`<article class="list-row action-row"><div><strong>${escapeHTML(item.title||item.action_type)}</strong><small>${escapeHTML(item.action_type)} · riesgo ${escapeHTML(item.risk)} · ${escapeHTML(item.status)}</small></div><div class="mission-actions">${item.status==='pending_approval'?`<button class="soft-btn mini-btn" data-action-decision="approved" data-action-id="${escapeHTML(item.id)}">Aprobar</button><button class="danger-btn mini-btn" data-action-decision="rejected" data-action-id="${escapeHTML(item.id)}">Rechazar</button>`:''}${item.status==='approved'?`<button class="primary-btn mini-btn" data-action-execute="${escapeHTML(item.id)}">Ejecutar</button>`:''}<span class="status-tag ${item.status==='completed'?'ok':item.status==='failed'?'danger':'warn'}">${escapeHTML(item.status)}</span></div></article>`).join(''):'<div class="empty-state">No hay acciones preparadas.</div>'}</div></section>
      <section class="panel-section"><div class="panel-section-head"><h3>Calidad y estabilidad</h3><button class="soft-btn" id="runQualitySuite">Ejecutar evaluación</button></div><article class="panel-card quality-card"><div><span class="card-kicker">ÚLTIMA MEDICIÓN</span><strong class="metric">${latestQuality.score===undefined?'—':Math.round(Number(latestQuality.score)*100)+'%'}</strong></div><p>${latestQuality.status?`Estado ${escapeHTML(latestQuality.status)}. La evaluación prueba base de datos, herramientas locales, memoria, rutas, frontend y seguridad.`:'Ejecuta la primera evaluación integral de esta instalación.'}</p></article></section>
      <section class="panel-section"><div class="panel-section-head"><h3>Integraciones</h3><span class="status-tag">las escrituras exigen confirmación</span></div><div class="integration-grid">${integrations.map(item=>`<article class="integration-card"><span>${icon(item.name==='telegram'?'telegram':'cpu')}</span><div><strong>${escapeHTML(item.label)}</strong><small>${escapeHTML((item.actions||[]).join(' · '))}</small></div><em class="status-tag ${item.configured?'ok':'warn'}">${item.configured?'Lista':'Configurar'}</em></article>`).join('')}</div></section>
      <section class="panel-section"><div class="panel-section-head"><h3>Resultados interactivos</h3><button class="soft-btn" id="newArtifact">Crear lista</button></div><div class="artifact-grid">${artifacts.length?artifacts.map(renderArtifactCard).join(''):'<div class="empty-state">Crea tablas, gráficas, listas y cronogramas seguros.</div>'}</div></section>
      <section class="panel-section"><div class="panel-section-head"><h3>Decisiones recientes</h3><span class="status-tag">${decisions.length}</span></div><div class="list-stack">${decisions.length?decisions.map(item=>`<article class="list-row"><div><strong>${escapeHTML(item.objective)}</strong><small>${escapeHTML(item.intent)} · ${escapeHTML(item.complexity)} · ${escapeHTML(item.status)}</small></div><span class="status-tag ${item.status==='completed'?'ok':'warn'}">${Math.round(Number(item.quality_score||0)*100)}%</span></article>`).join(''):'<div class="empty-state">Las decisiones aparecerán al conversar o ejecutar misiones.</div>'}</div></section>`;
    $('#nexusDiagnostics')?.addEventListener('click',()=>openView('system'));
    const runPlan=async execute=>{
      const objective=$('#nexusObjective').value.trim(); if(!objective)return toast('Escribe un objetivo concreto.');
      const button=execute?$('#runNexusPlan'):$('#previewNexusPlan'); button.disabled=true; button.textContent=execute?'Iniciando…':'Planificando…';
      try{
        const data=await request(execute?'/api/intelligence/execute':'/api/intelligence/plan',{method:'POST',body:JSON.stringify({session_id:backendSessionId(),objective,mode:$('#nexusMode').value,project_name:'General',title:'Misión JARVIS'})},{timeoutMs:30000});
        const plan=data.plan||{}; $('#nexusPlanResult').hidden=false; $('#nexusPlanResult').innerHTML=`<strong>${escapeHTML(plan.complexity||'low')} · ${Number(plan.steps?.length||0)} etapas</strong><p>Tiempo objetivo: ${Number(plan.budget?.time_seconds||0)} s · rutas: ${(plan.route||[]).map(item=>escapeHTML(item.provider)).join(' → ')||'herramientas locales'}</p>`;
        if(execute){toast('Misión iniciada con checkpoints');setTimeout(()=>openView('missions'),650);}
      }catch(error){toast(explainError(error));}finally{button.disabled=false;button.textContent=execute?'Ejecutar':'Ver plan';}
    };
    $('#previewNexusPlan')?.addEventListener('click',()=>runPlan(false));
    $('#runNexusPlan')?.addEventListener('click',()=>runPlan(true));
    $('#prepareAction')?.addEventListener('click',async()=>{
      const type=$('#actionType').value,target=$('#actionTarget').value.trim(),content=$('#actionContent').value.trim(),schedule=$('#actionSchedule').value.trim();
      if(!content)return toast('Escribe el contenido o las instrucciones.');
      let args={};
      if(type==='memory.save')args={content,category:'fact',importance:3};
      if(type==='reminder.create')args={title:target||content,due_at:schedule};
      if(type==='automation.create')args={title:target||'Automatización JARVIS',prompt:content,schedule_type:/^\d+$/.test(schedule)?'interval':'once',schedule_value:schedule};
      if(type==='telegram.notify')args={recipient:target,message:content};
      if((type==='telegram.notify'&&!target)||(type==='reminder.create'&&!schedule)||(type==='automation.create'&&!schedule))return toast('Completa el destinatario o la programación requerida.');
      const button=$('#prepareAction');button.disabled=true;
      try{await request('/api/actions',{method:'POST',body:JSON.stringify({session_id:backendSessionId(),action_type:type,title:target||type,arguments:args})});toast('Acción preparada para revisión');renderNexus();}
      catch(error){toast(explainError(error));button.disabled=false;}
    });
    $$('[data-action-decision]').forEach(button=>button.addEventListener('click',async()=>{
      const decision=button.dataset.actionDecision,id=button.dataset.actionId;
      if(!confirm(decision==='approved'?'¿Aprobar esta acción? Aún no se ejecutará.':'¿Rechazar esta acción?'))return;
      await request(`/api/actions/${encodeURIComponent(id)}/decision`,{method:'POST',body:JSON.stringify({session_id:backendSessionId(),decision,note:''})});renderNexus();
    }));
    $$('[data-action-execute]').forEach(button=>button.addEventListener('click',async()=>{
      if(!confirm('¿Ejecutar ahora la acción aprobada?'))return;
      button.disabled=true;try{await request(`/api/actions/${encodeURIComponent(button.dataset.actionExecute)}/execute`,{method:'POST',body:JSON.stringify({session_id:backendSessionId()})},{timeoutMs:45000});toast('Acción ejecutada');renderNexus();}catch(error){toast(explainError(error));button.disabled=false;}
    }));
    $('#runQualitySuite')?.addEventListener('click',async()=>{
      const button=$('#runQualitySuite');button.disabled=true;button.textContent='Evaluando…';
      try{const data=await request(`/api/evaluations/suite?session_id=${sid}`,{method:'POST'},{timeoutMs:45000});toast(`Evaluación ${Math.round(Number(data.suite?.score||0)*100)}%`);renderNexus();}catch(error){toast(explainError(error));button.disabled=false;button.textContent='Ejecutar evaluación';}
    });
    $('#newArtifact')?.addEventListener('click',async()=>{
      const title=prompt('Nombre de la lista'); if(!title)return;
      const raw=prompt('Elementos, uno por línea'); if(!raw)return;
      await request('/api/artifacts',{method:'POST',body:JSON.stringify({session_id:backendSessionId(),title,artifact_type:'checklist',spec:{title,items:raw.split(/\n+/).filter(Boolean)}})});
      toast('Resultado interactivo creado');renderNexus();
    });
  }

  async function renderMissions() {
    const data = await request(`/api/autonomy/workflows?session_id=${encodeURIComponent(backendSessionId())}&limit=20`);
    const workflows = data.workflows || [];
    els.panelContent.innerHTML = `
      <div class="mission-intro panel-card"><div><span class="card-kicker">EJECUCIÓN AUTÓNOMA CONTROLADA</span><h3>Nueva misión</h3><p>JARVIS define presupuesto, selecciona rutas, guarda checkpoints y solicita permiso antes de cualquier acción sensible.</p></div><div class="mission-legend"><span>01 Plan</span><span>02 Ejecuta</span><span>03 Verifica</span></div></div>
      <section class="panel-section"><div class="panel-card"><div class="form-grid mission-form"><input class="text-input" id="missionObjective" placeholder="Describe el resultado que necesitas"/><select class="text-input" id="missionMode"><option value="auto">Automático</option><option value="research">Investigación</option><option value="professional">Profesional</option><option value="private">Privado/local</option></select><button class="primary-btn" id="createMission">Iniciar misión</button></div></div></section>
      <section class="panel-section"><div class="panel-section-head"><h3>Misiones recientes</h3><span class="status-tag">${workflows.length}</span></div><div class="list-stack mission-list">${workflows.length ? workflows.map(item => { const steps=item.steps||[]; const done=steps.filter(step=>step.status==='completed').length; const progress=steps.length?Math.round(done/steps.length*100):0; const active=['queued','running','pausing'].includes(item.status); return `<article class="list-row mission-row"><div><strong>${escapeHTML(item.objective || 'Misión')}</strong><small>${escapeHTML(item.status || 'planned')} · ${done}/${steps.length} etapas<div class="job-progress"><i style="width:${progress}%"></i></div></small></div><div class="mission-actions"><span class="status-tag ${item.status==='completed'?'ok':'warn'}">${progress}%</span>${active?`<button class="soft-btn mini-btn" data-mission-action="pause" data-mission-id="${escapeHTML(item.id)}">Pausar</button>`:''}${['paused','failed','planned'].includes(item.status)?`<button class="soft-btn mini-btn" data-mission-action="start" data-mission-id="${escapeHTML(item.id)}">Continuar</button>`:''}${!['completed','cancelled','rejected'].includes(item.status)?`<button class="danger-btn mini-btn" data-mission-action="cancel" data-mission-id="${escapeHTML(item.id)}">Cancelar</button>`:''}</div></article>`; }).join('') : '<div class="empty-state">No hay misiones todavía.</div>'}</div></section>`;
    $('#createMission').addEventListener('click', async () => {
      const objective = $('#missionObjective').value.trim(); if (!objective) return;
      const button=$('#createMission'); button.disabled=true; button.textContent='Creando…';
      try {
        await request('/api/intelligence/execute', { method:'POST', body:JSON.stringify({ session_id:backendSessionId(), objective, mode:$('#missionMode').value, project_name:'General', title:'Misión JARVIS' }) }, { timeoutMs:30000 });
        toast('Misión iniciada con presupuesto y checkpoints'); renderMissions();
      } catch(error) { toast(explainError(error)); button.disabled=false; button.textContent='Iniciar misión'; }
    });
    $$('[data-mission-action]').forEach(button=>button.addEventListener('click',async()=>{
      const action=button.dataset.missionAction,id=button.dataset.missionId;
      if(action==='cancel'&&!confirm('¿Cancelar esta misión?'))return;
      button.disabled=true;
      try{
        await request(`/api/autonomy/workflows/${encodeURIComponent(id)}/${action}?session_id=${encodeURIComponent(backendSessionId())}`,{method:'POST'});
        toast(action==='pause'?'Misión pausada':action==='cancel'?'Misión cancelada':'Misión reanudada');renderMissions();
      }catch(error){toast(explainError(error));button.disabled=false;}
    }));
  }

  async function renderChannels() {
    const data = await request('/api/channels/status');
    const telegram = data.channels?.telegram || data.telegram || {};
    const multimodal = data.multimodal || {};
    const preferences = data.preferences || {};
    const base = state.apiBase || location.origin;
    els.panelContent.innerHTML = `
      <div class="panel-grid">
        <article class="panel-card channel-card"><span class="channel-icon">${icon('telegram')}</span><div><h3>Telegram Pro</h3><p>${telegram.configured ? 'Texto, imágenes, notas de voz, documentos y misiones.' : 'Agrega las variables de Telegram en Render.'}</p></div><span class="status-tag ${telegram.configured?'ok':'warn'}">${telegram.configured?'Operativo':'Pendiente'}</span></article>
        <article class="panel-card channel-card"><span class="channel-icon">${icon('file')}</span><div><h3>Comprensión multimedia</h3><p>Imágenes ${multimodal.vision?'listas':'pendientes'} · transcripción ${multimodal.transcription?'lista':'pendiente'}.</p></div><span class="status-tag ${multimodal.vision&&multimodal.transcription?'ok':'warn'}">${multimodal.vision&&multimodal.transcription?'Completa':'Revisar'}</span></article>
        <article class="panel-card channel-card"><span class="channel-icon">${icon('volume')}</span><div><h3>Respuesta de voz</h3><p>${multimodal.speech ? `${preferences.voice_enabled||0} chat(s) con voz activa.` : 'Configura OpenAI para generar audio.'}</p></div><span class="status-tag ${multimodal.speech?'ok':'warn'}">${multimodal.speech?'Disponible':'Opcional'}</span></article>
      </div>
      <section class="panel-section"><div class="panel-card"><h3>Conexión segura</h3><p>Webhook: <code>${escapeHTML(base)}/api/channels/telegram/webhook</code></p><p style="margin-top:8px">El botón registra la URL y habilita mensajes y botones interactivos.</p><button class="soft-btn" id="registerTelegram" style="margin-top:12px" ${telegram.configured?'':'disabled'}>Registrar webhook</button></div></section>
      <section class="panel-section"><div class="panel-card"><h3>Funciones desde Telegram</h3><p><code>/menu</code> · <code>/status</code> · <code>/new</code> · <code>/mission objetivo</code> · <code>/tasks</code> · <code>/stop ID</code> · <code>/voice on|off</code> · <code>/export</code></p></div></section>
      <section class="panel-section"><div class="panel-card"><h3>Enviar mensaje de prueba</h3><div class="form-grid" style="margin-top:13px"><input class="text-input" id="channelRecipient" placeholder="Chat ID de Telegram"/><button class="primary-btn" id="sendChannelTest">Preparar envío</button></div><textarea class="text-input" id="channelMessage" placeholder="Mensaje" style="margin-top:8px;min-height:80px"></textarea></div></section>`;
    $('#registerTelegram').addEventListener('click', async () => {
      if (!confirm('¿Registrar el webhook seguro de Telegram?')) return;
      await request('/api/channels/telegram/register-webhook', { method:'POST', body:JSON.stringify({ webhook_url:`${base}/api/channels/telegram/webhook`, drop_pending_updates:false }) });
      toast('Webhook registrado'); renderChannels();
    });
    $('#sendChannelTest').addEventListener('click', async () => {
      const channel='telegram', recipient=$('#channelRecipient').value.trim(), message=$('#channelMessage').value.trim();
      if (!recipient || !message) return toast('Completa destinatario y mensaje.');
      if (!confirm(`¿Confirmas enviar este mensaje por ${channel}?`)) return;
      await request('/api/channels/send', { method:'POST', body:JSON.stringify({ channel, recipient, message, confirmed:true }) }, { timeoutMs:30000 });
      toast('Mensaje enviado');
    });
  }

  async function renderSystem() {
    const checks = await Promise.allSettled([
      request('/api/health/live'), request('/api/health/ready'), request('/api/auth/status'), request('/api/providers')
    ]);
    const live = valueOf(checks[0]), ready=valueOf(checks[1]), auth=valueOf(checks[2]), providers=valueOf(checks[3]);
    const configured = Number(providers.configured_count || providers.gateway?.configured?.length || 0);
    els.panelContent.innerHTML = `
      <div class="panel-grid">
        <article class="panel-card"><h3>Proceso</h3><strong class="metric">${live.status==='ok'?'Operativo':'Revisar'}</strong><p>Versión ${escapeHTML(live.version || state.core.version || '—')}</p></article>
        <article class="panel-card"><h3>Preparación</h3><strong class="metric">${ready.status==='ready'?'Lista':'Revisar'}</strong><p>Base de datos y recursos de interfaz.</p></article>
        <article class="panel-card"><h3>Acceso</h3><strong class="metric">${auth.authenticated?'Conectado':auth.auth_required?'Privado':'Público'}</strong><p>${auth.authenticated?'Sesión válida':auth.auth_required?'Inicia sesión para utilizar funciones':'No requiere sesión'}</p></article>
        <article class="panel-card"><h3>Proveedores</h3><strong class="metric">${configured}</strong><p>Rutas generativas configuradas.</p></article>
      </div>
      <section class="panel-section"><div class="panel-card"><h3>Dirección activa</h3><p><code>${escapeHTML(state.apiBase || location.origin)}</code></p><div class="button-row"><button class="soft-btn" id="openConnectionSettings">Cambiar conexión</button><button class="soft-btn" id="openAccountSettings">Cuenta personal</button></div></div></section>`;
    $('#openConnectionSettings').addEventListener('click', openConnection);
    $('#openAccountSettings').addEventListener('click', () => openAccount(false));
  }

  function valueOf(result) { return result.status === 'fulfilled' ? result.value : {}; }

  async function openAccount(force = false) {
    closeSidebar();
    try {
      const data = await request('/api/auth/status', {}, { attempts:1, timeoutMs:12000 });
      state.auth = { required:Boolean(data.auth_required), registration:Boolean(data.registration_enabled), authenticated:Boolean(data.authenticated) };
      state.user = data.user || null;
      if (data.authenticated) {
        updateAccountUI();
        if (force) return;
        const logout = confirm(`Sesión activa: ${data.user?.email || 'cuenta personal'}\n\n¿Cerrar sesión?`);
        if (logout) {
          await request('/api/auth/logout', { method:'POST' }).catch(()=>({}));
          clearSession(); updateAccountUI(); toast('Sesión cerrada'); openAccount(true);
        }
        return;
      }
      if (state.token) clearSession();
      els.registerTab.hidden = !data.registration_enabled;
      setAuthMode(data.first_user_pending && data.registration_enabled ? 'register' : 'login');
      els.authCopy.textContent = data.first_user_pending ? 'Crea la primera cuenta propietaria para activar JARVIS.' : 'Inicia sesión para utilizar las funciones privadas.';
      if (!els.authModal.open) els.authModal.showModal();
    } catch (error) {
      els.connectionExplanation.textContent = explainError(error);
      openConnection();
    }
  }

  function setAuthMode(mode) {
    state.authMode = mode;
    $$('[data-auth-tab]').forEach(button => button.classList.toggle('active', button.dataset.authTab === mode));
    els.nameField.hidden = mode !== 'register';
    els.authTitle.textContent = mode === 'register' ? 'Crea tu cuenta propietaria' : 'Bienvenido de nuevo';
    els.authSubmit.textContent = mode === 'register' ? 'Crear cuenta y conectar' : 'Iniciar sesión';
    els.authPassword.autocomplete = mode === 'register' ? 'new-password' : 'current-password';
    els.authError.hidden = true;
  }

  async function submitAuth(event) {
    event.preventDefault();
    const email=els.authEmail.value.trim(), password=els.authPassword.value;
    const payload = state.authMode === 'register' ? { display_name:els.authName.value.trim(), email, password } : { email, password };
    els.authSubmit.disabled = true; els.authSubmit.textContent = 'Conectando…'; els.authError.hidden = true;
    try {
      const result = await request(state.authMode === 'register' ? '/api/auth/register' : '/api/auth/login', { method:'POST', body:JSON.stringify(payload) }, { timeoutMs:20000 });
      state.token=result.token || ''; state.user=result.user || null; state.auth.authenticated=true;
      session.setItem(KEYS.token,state.token); saveUser(); updateAccountUI();
      els.authModal.close(); setStatus('Núcleo operativo','online'); toast('Cuenta conectada');
      startNotificationPolling();
    } catch(error) {
      els.authError.textContent = explainError(error); els.authError.hidden=false;
    } finally {
      els.authSubmit.disabled=false; els.authSubmit.textContent=state.authMode==='register'?'Crear cuenta y conectar':'Iniciar sesión';
    }
  }

  function saveUser() { session.setItem(KEYS.user, JSON.stringify(state.user || null)); }
  function clearSession() { state.token=''; state.user=null; state.auth.authenticated=false; session.removeItem(KEYS.token); session.removeItem(KEYS.user); }
  function updateAccountUI() {
    const name=state.user?.display_name || 'Cuenta personal';
    els.accountName.textContent=name;
    els.accountState.textContent=state.auth.authenticated?'Sesión protegida':state.auth.required?'Inicia sesión':'Acceso opcional';
    els.avatar.textContent=(name.trim()[0] || 'C').toUpperCase();
  }

  function openConnection() {
    closeSidebar();
    els.apiBaseInput.value=state.apiBase || (isGitHubPages?configuredBase:location.origin);
    els.connectionResult.textContent='';
    if (!els.connectionModal.open) els.connectionModal.showModal();
  }

  async function saveConnection() {
    const value=normalizeBase(els.apiBaseInput.value);
    if (!/^https?:\/\//i.test(value)) { els.connectionResult.textContent='Escribe una URL completa que comience con https://'; return; }
    state.apiBase = (!isGitHubPages && value === normalizeBase(location.origin)) ? '' : value;
    if (state.apiBase) local.setItem(KEYS.api,state.apiBase); else local.removeItem(KEYS.api);
    await testConnection();
  }

  async function testConnection() {
    els.connectionResult.textContent='Comprobando…';
    const ok=await bootCore();
    if (ok) { els.connectionResult.textContent='✓ Núcleo conectado correctamente.'; setTimeout(()=>els.connectionModal.close(),650); }
    else els.connectionResult.textContent='No se pudo conectar. Confirma que Render esté Live y que esta sea la URL del Web Service.';
  }

  let notificationTimer;
  function startNotificationPolling() {
    if (notificationTimer) return;
    notificationTimer=setInterval(async()=>{
      if (!state.core.online || (state.auth.required && !state.auth.authenticated)) return;
      try {
        const data=await request(`/api/notifications?session_id=${encodeURIComponent(backendSessionId())}`,{}, { attempts:1,timeoutMs:12000 });
        (data.notifications||[]).forEach(item=>toast(`Recordatorio: ${item.title}`));
      } catch { /* Las notificaciones no cambian el estado del núcleo. */ }
    },60000);
  }

  function startVoiceInput() {
    const Recognition=window.SpeechRecognition||window.webkitSpeechRecognition;
    if (!Recognition) return toast('El dictado no está disponible en este navegador.');
    const recognition=new Recognition(); recognition.lang='es-HN'; recognition.interimResults=false;
    recognition.onstart=()=>{ els.voiceBtn.classList.add('listening'); els.voiceBtn.setAttribute('aria-label','Escuchando; pulsa para detener'); };
    recognition.onresult=event=>{ els.messageInput.value=`${els.messageInput.value} ${event.results[0][0].transcript}`.trim(); autoResize(); };
    recognition.onerror=()=>toast('No fue posible utilizar el micrófono.');
    recognition.onend=()=>{ els.voiceBtn.classList.remove('listening'); els.voiceBtn.setAttribute('aria-label','Dictar mensaje'); };
    recognition.start();
  }

  function toast(message) {
    clearTimeout(state.toastTimer); els.toast.textContent=String(message||''); els.toast.classList.add('show');
    state.toastTimer=setTimeout(()=>els.toast.classList.remove('show'),3200);
  }

  function registerServiceWorker() {
    if (!('serviceWorker' in navigator) || location.protocol === 'file:') return;
    navigator.serviceWorker.register('./service-worker.js?v=65.1').catch(()=>{});
  }
})();
