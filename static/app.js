(() => {
  'use strict';

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

  const els = {
    ambient: $('#ambientGlow'),
    statusPill: $('#statusPill'),
    statusText: $('#statusText'),
    menuBtn: $('#menuBtn'),
    workspaceBtn: $('#workspaceBtn'),
    newChatTopBtn: $('#newChatTopBtn'),
    chatScroll: $('#chatScroll'),
    welcome: $('#welcome'),
    messages: $('#messages'),
    thinkingWrap: $('#thinkingWrap'),
    thinkingText: $('#thinkingText'),
    jumpBtn: $('#jumpBtn'),
    attachments: $('#attachments'),
    attachBtn: $('#attachBtn'),
    fileInput: $('#fileInput'),
    userInput: $('#userInput'),
    micBtn: $('#micBtn'),
    sendBtn: $('#sendBtn'),
    sendIcon: $('#sendIcon'),
    modeBtn: $('#modeBtn'),
    backdrop: $('#backdrop'),
    drawer: $('#drawer'),
    closeDrawerBtn: $('#closeDrawerBtn'),
    newChatBtn: $('#newChatBtn'),
    chatList: $('#chatList'),
    sheet: $('#sheet'),
    sheetTitle: $('#sheetTitle'),
    sheetBody: $('#sheetBody'),
    closeSheetBtn: $('#closeSheetBtn'),
    toast: $('#toast')
  };

  const STORE = {
    client: 'jarvis_nexus_client',
    chats: 'jarvis_nexus_chats',
    active: 'jarvis_nexus_active_chat',
    draftPrefix: 'jarvis_nexus_draft_',
    apiBase: 'jarvis_pages_api_base_v7',
    mode: 'jarvis_nexus_mode'
  };

  const MODES = [
    { id: 'auto', label: 'Modo automático' },
    { id: 'fast', label: 'Modo rápido' },
    { id: 'research', label: 'Modo investigación' },
    { id: 'math', label: 'Modo matemática' },
    { id: 'writing', label: 'Modo escritura' }
  ];

  const IS_GITHUB_PAGES = location.hostname.endsWith('.github.io');
  const CONFIGURED_API_BASE = normalizeBase(window.JARVIS_CONFIG?.API_BASE || '');
  const DEFAULT_API_BASE = IS_GITHUB_PAGES
    ? CONFIGURED_API_BASE
    : normalizeBase(location.origin || CONFIGURED_API_BASE);

  const state = {
    clientId: localStorage.getItem(STORE.client) || uid('client'),
    chats: loadJSON(STORE.chats, {}),
    activeChatId: localStorage.getItem(STORE.active) || '',
    files: [],
    isGenerating: false,
    abortController: null,
    thinkingTimer: null,
    statusTimers: [],
    followOutput: true,
    mode: localStorage.getItem(STORE.mode) || 'auto',
    apiBase: normalizeBase(localStorage.getItem(STORE.apiBase) || DEFAULT_API_BASE),
    lastPrompt: '',
    wakeRetrying: false
  };

  localStorage.setItem(STORE.client, state.clientId);

  document.addEventListener('DOMContentLoaded', init);

  function init() {
    if (!state.activeChatId || !state.chats[state.activeChatId]) createChat(false);
    configureMarkdown();
    bindEvents();
    renderMode();
    renderChatList();
    renderActiveChat();
    restoreDraft();
    autoResize();
    checkHealth({ wake: true });
    pollNotifications();
  }

  function bindEvents() {
    els.menuBtn.addEventListener('click', openDrawer);
    els.closeDrawerBtn.addEventListener('click', closeOverlays);
    els.backdrop.addEventListener('click', closeOverlays);
    els.workspaceBtn.addEventListener('click', () => openPanel('overview'));
    els.closeSheetBtn.addEventListener('click', closeOverlays);
    els.newChatTopBtn.addEventListener('click', () => createChat(true));
    els.newChatBtn.addEventListener('click', () => createChat(true));

    $$('.drawer-link').forEach(btn => btn.addEventListener('click', () => openPanel(btn.dataset.panel)));
    $$('.suggestion').forEach(btn => btn.addEventListener('click', () => {
      els.userInput.value = btn.dataset.prompt || '';
      saveDraft();
      autoResize();
      els.userInput.focus();
    }));

    els.attachBtn.addEventListener('click', () => els.fileInput.click());
    els.fileInput.addEventListener('change', handleFiles);
    els.sendBtn.addEventListener('click', handlePrimaryAction);
    els.micBtn.addEventListener('click', startVoiceInput);
    els.modeBtn.addEventListener('click', cycleMode);
    els.jumpBtn.addEventListener('click', () => scrollToBottom(true));

    els.userInput.addEventListener('input', () => { autoResize(); saveDraft(); });
    els.userInput.addEventListener('keydown', e => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handlePrimaryAction();
      }
    });

    els.chatScroll.addEventListener('scroll', () => {
      state.followOutput = isNearBottom();
      els.jumpBtn.classList.toggle('show', !state.followOutput && state.isGenerating);
    });

    window.addEventListener('online', () => checkHealth({ wake: true }));
    window.addEventListener('offline', () => setStatus('Sin conexión', 'error'));
  }

  function configureMarkdown() {
    if (!window.marked) return;
    marked.setOptions({ gfm: true, breaks: true });
  }

  function uid(prefix = 'id') {
    if (crypto?.randomUUID) return `${prefix}_${crypto.randomUUID()}`;
    return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`;
  }

  function normalizeBase(value) {
    return String(value || '').trim().replace(/\/+$/, '');
  }

  function apiUrl(path) {
    const base = normalizeBase(state.apiBase || DEFAULT_API_BASE);
    if (!base) throw new Error('No se ha configurado la URL del backend de JARVIS.');
    return `${base}${path}`;
  }

  function loadJSON(key, fallback) {
    try { return JSON.parse(localStorage.getItem(key) || '') || fallback; }
    catch { return fallback; }
  }

  function saveChats() {
    localStorage.setItem(STORE.chats, JSON.stringify(state.chats));
    localStorage.setItem(STORE.active, state.activeChatId);
  }

  function currentChat() {
    return state.chats[state.activeChatId];
  }

  function backendConversationId(chatId = state.activeChatId) {
    return `public_${state.clientId}_${chatId}`.replace(/[^a-zA-Z0-9_.:@-]/g, '_').slice(0, 150);
  }

  function createChat(showToast = true) {
    if (state.isGenerating) stopGeneration();
    const id = uid('chat');
    state.chats[id] = { id, title: 'Nueva conversación', messages: [], createdAt: Date.now(), updatedAt: Date.now() };
    state.activeChatId = id;
    saveChats();
    renderChatList();
    renderActiveChat();
    restoreDraft();
    closeOverlays();
    if (showToast) toast('Nueva conversación creada');
    els.userInput.focus();
  }

  function removeChat(id) {
    delete state.chats[id];
    localStorage.removeItem(STORE.draftPrefix + id);
    const remaining = Object.keys(state.chats);
    state.activeChatId = remaining[0] || '';
    if (!state.activeChatId) createChat(false);
    saveChats();
    renderChatList();
    renderActiveChat();
  }

  function switchChat(id) {
    if (!state.chats[id]) return;
    if (state.isGenerating) stopGeneration();
    state.activeChatId = id;
    saveChats();
    renderChatList();
    renderActiveChat();
    restoreDraft();
    closeOverlays();
  }

  function renderChatList() {
    const items = Object.values(state.chats).sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0));
    els.chatList.innerHTML = '';
    if (!items.length) {
      els.chatList.innerHTML = '<div class="empty-note">No hay conversaciones todavía.</div>';
      return;
    }
    items.forEach(chat => {
      const btn = document.createElement('button');
      btn.className = `chat-item${chat.id === state.activeChatId ? ' active' : ''}`;
      btn.textContent = chat.title || 'Conversación';
      btn.title = chat.title || 'Conversación';
      btn.addEventListener('click', () => switchChat(chat.id));
      btn.addEventListener('contextmenu', e => {
        e.preventDefault();
        if (confirm('¿Eliminar esta conversación?')) removeChat(chat.id);
      });
      els.chatList.appendChild(btn);
    });
  }

  function renderActiveChat() {
    els.messages.innerHTML = '';
    const chat = currentChat();
    const hasMessages = Boolean(chat?.messages?.length);
    els.welcome.style.display = hasMessages ? 'none' : 'flex';
    if (!hasMessages) return;
    chat.messages.forEach(msg => {
      if (msg.role === 'user') appendUser(msg.content, false, msg.files || []);
      else appendAssistant(msg.content, msg.meta || {}, false, false);
    });
    requestAnimationFrame(() => scrollToBottom(false));
  }

  function saveDraft() {
    localStorage.setItem(STORE.draftPrefix + state.activeChatId, els.userInput.value);
  }

  function restoreDraft() {
    els.userInput.value = localStorage.getItem(STORE.draftPrefix + state.activeChatId) || '';
    autoResize();
  }

  function clearDraft() {
    localStorage.removeItem(STORE.draftPrefix + state.activeChatId);
  }

  function autoResize() {
    els.userInput.style.height = 'auto';
    els.userInput.style.height = `${Math.min(els.userInput.scrollHeight, 190)}px`;
  }

  function cycleMode() {
    const index = MODES.findIndex(m => m.id === state.mode);
    state.mode = MODES[(index + 1) % MODES.length].id;
    localStorage.setItem(STORE.mode, state.mode);
    renderMode();
  }

  function renderMode() {
    els.modeBtn.textContent = MODES.find(m => m.id === state.mode)?.label || MODES[0].label;
  }

  async function handleFiles(event) {
    const chosen = [...(event.target.files || [])].slice(0, 3 - state.files.length);
    for (const file of chosen) {
      if (file.size > 12 * 1024 * 1024) {
        toast(`${file.name} supera el límite de 12 MB`);
        continue;
      }
      try {
        const file_b64 = await readAsDataURL(file);
        state.files.push({ file_name: file.name, file_b64, size: file.size });
      } catch {
        toast(`No se pudo leer ${file.name}`);
      }
    }
    event.target.value = '';
    renderAttachments();
  }

  function readAsDataURL(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
  }

  function renderAttachments() {
    els.attachments.innerHTML = '';
    state.files.forEach((file, index) => {
      const chip = document.createElement('div');
      chip.className = 'file-chip';
      chip.innerHTML = `<span title="${escapeHtml(file.file_name)}">${escapeHtml(file.file_name)}</span><button aria-label="Quitar archivo">×</button>`;
      chip.querySelector('button').addEventListener('click', () => {
        state.files.splice(index, 1);
        renderAttachments();
      });
      els.attachments.appendChild(chip);
    });
  }

  function handlePrimaryAction() {
    if (state.isGenerating) stopGeneration();
    else sendMessage();
  }

  async function sendMessage(textOverride = '') {
    const text = (textOverride || els.userInput.value).trim();
    if ((!text && !state.files.length) || state.isGenerating) return;

    state.isGenerating = true;
    state.lastPrompt = text;
    state.followOutput = true;
    state.abortController = new AbortController();
    setSendState(true);
    els.welcome.style.display = 'none';

    const fileNames = state.files.map(f => f.file_name);
    appendUser(text || 'Analiza los archivos adjuntos.', true, fileNames);
    persistMessage({ role: 'user', content: text || 'Analiza los archivos adjuntos.', files: fileNames });

    const outgoingFiles = state.files.map(({ file_name, file_b64 }) => ({ file_name, file_b64 }));
    state.files = [];
    renderAttachments();
    els.userInput.value = '';
    clearDraft();
    autoResize();

    scheduleThinking();
    startStatusSequence();

    try {
      const response = await fetch(apiUrl('/api/jarvis'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: text || 'Analiza los archivos adjuntos.',
          session_id: backendConversationId(),
          files: outgoingFiles
        }),
        signal: state.abortController.signal
      });

      const raw = await response.text();
      let data;
      try { data = JSON.parse(raw); }
      catch { throw new Error(`El servidor respondió con contenido no válido (HTTP ${response.status}).`); }

      if (!response.ok) {
        const retry = data.retry_after_seconds ? ` Intenta nuevamente en ${data.retry_after_seconds} segundos.` : '';
        throw new Error((data.detail || data.reply || `Error HTTP ${response.status}`) + retry);
      }

      hideThinking();
      const reply = data.reply || data.response || 'El núcleo no devolvió contenido.';
      const meta = {
        tools: data.tools || [],
        model: data.model || '',
        cached: Boolean(data.cached),
        degraded: Boolean(data.degraded),
        mode: data.mode || ''
      };
      appendAssistant(reply, meta, true, true);
      persistMessage({ role: 'assistant', content: reply, meta });
      updateChatTitle(text);
    } catch (error) {
      hideThinking();
      if (error.name === 'AbortError') {
        const partial = 'Generación detenida por el usuario.';
        appendAssistant(partial, { cancelled: true }, true, false);
        persistMessage({ role: 'assistant', content: partial, meta: { cancelled: true } });
      } else {
        const friendly = `⚠️ **No fue posible completar la solicitud.**\n\n${error.message || 'Error desconocido.'}\n\nJARVIS conservará las funciones locales y puedes volver a intentarlo.`;
        appendAssistant(friendly, { error: true }, true, false);
        persistMessage({ role: 'assistant', content: friendly, meta: { error: true } });
      }
    } finally {
      state.isGenerating = false;
      state.abortController = null;
      setSendState(false);
      clearStatusSequence();
      els.ambient.classList.remove('active');
      els.jumpBtn.classList.remove('show');
    }
  }

  function stopGeneration() {
    state.abortController?.abort();
    hideThinking();
    clearStatusSequence();
    els.ambient.classList.remove('active');
  }

  function setSendState(generating) {
    els.sendBtn.title = generating ? 'Detener' : 'Enviar';
    els.sendBtn.setAttribute('aria-label', generating ? 'Detener' : 'Enviar');
    els.sendIcon.innerHTML = generating
      ? '<path d="M7 7h10v10H7z"/>'
      : '<path d="M3.4 20.4 21 12 3.4 3.6 3 10l12 2-12 2z"/>';
  }

  function scheduleThinking() {
    clearTimeout(state.thinkingTimer);
    state.thinkingTimer = setTimeout(() => {
      if (!state.isGenerating) return;
      els.thinkingWrap.classList.add('active');
      els.ambient.classList.add('active');
      followBottom();
    }, 220);
  }

  function hideThinking() {
    clearTimeout(state.thinkingTimer);
    els.thinkingWrap.classList.remove('active');
  }

  function startStatusSequence() {
    clearStatusSequence();
    const states = state.mode === 'research'
      ? ['Preparando investigación', 'Buscando información actual', 'Revisando fuentes', 'Comparando resultados', 'Redactando respuesta']
      : ['Preparando respuesta', 'Analizando contexto', 'Seleccionando herramientas', 'Construyendo respuesta'];
    let index = 0;
    els.thinkingText.textContent = states[0];
    const tick = () => {
      if (!state.isGenerating) return;
      index = Math.min(index + 1, states.length - 1);
      els.thinkingText.animate([{ opacity: 0, transform: 'translateY(3px)' }, { opacity: 1, transform: 'none' }], { duration: 180, easing: 'ease-out' });
      els.thinkingText.textContent = states[index];
      if (index < states.length - 1) state.statusTimers.push(setTimeout(tick, 2300));
    };
    state.statusTimers.push(setTimeout(tick, 1800));
  }

  function clearStatusSequence() {
    state.statusTimers.forEach(clearTimeout);
    state.statusTimers = [];
  }

  function appendUser(text, scroll = true, files = []) {
    const row = document.createElement('div');
    row.className = 'message user';
    const fileText = files?.length ? `\n\n📎 ${files.join(', ')}` : '';
    row.innerHTML = `<div class="user-bubble">${escapeHtml(text + fileText)}</div>`;
    els.messages.appendChild(row);
    if (scroll) followBottom();
  }

  function appendAssistant(text, meta = {}, scroll = true, animateBlocks = true) {
    const row = document.createElement('div');
    row.className = 'message assistant';
    const avatar = document.createElement('img');
    avatar.className = 'assistant-avatar';
    const reactorRef = document.querySelector('.brand-reactor')?.getAttribute('src') || './static/jarvis-reactor.svg';
    avatar.src = new URL(reactorRef, document.baseURI).href;
    avatar.alt = 'JARVIS';

    const body = document.createElement('div');
    const content = document.createElement('div');
    content.className = 'assistant-content';
    body.appendChild(content);

    const grid = document.createElement('div');
    grid.className = 'assistant-row';
    grid.append(avatar, body);
    row.appendChild(grid);
    els.messages.appendChild(row);

    const html = renderMarkdown(text);
    if (animateBlocks && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) revealHtmlBlocks(content, html);
    else {
      content.innerHTML = html;
      finalizeRichContent(content);
    }

    const tools = Array.isArray(meta.tools) ? meta.tools : [];
    if (tools.length || meta.cached || meta.degraded) {
      const toolRow = document.createElement('div');
      toolRow.className = 'tool-row';
      tools.forEach(tool => {
        const name = typeof tool === 'string' ? tool : (tool.name || tool.tool || 'Herramienta');
        toolRow.insertAdjacentHTML('beforeend', `<span class="tool-chip">${escapeHtml(humanToolName(name))}</span>`);
      });
      if (meta.cached) toolRow.insertAdjacentHTML('beforeend', '<span class="tool-chip">Respuesta en caché</span>');
      if (meta.degraded) toolRow.insertAdjacentHTML('beforeend', '<span class="tool-chip">Modo degradado</span>');
      body.appendChild(toolRow);
    }

    const actions = buildActions(text, meta);
    body.appendChild(actions);
    requestAnimationFrame(() => actions.classList.add('visible'));

    if (scroll) followBottom();
  }

  function renderMarkdown(text) {
    if (!window.marked || !window.DOMPurify) return `<p>${escapeHtml(text).replace(/\n/g, '<br>')}</p>`;
    return DOMPurify.sanitize(marked.parse(text));
  }

  function revealHtmlBlocks(container, html) {
    const template = document.createElement('template');
    template.innerHTML = html.trim();
    const nodes = [...template.content.childNodes];
    let index = 0;
    const step = () => {
      if (index >= nodes.length) {
        finalizeRichContent(container);
        followBottom();
        return;
      }
      const node = nodes[index++];
      if (node.nodeType === Node.ELEMENT_NODE) node.classList.add('reveal-block');
      container.appendChild(node);
      followBottom();
      setTimeout(step, nodes.length > 10 ? 28 : 45);
    };
    step();
  }

  function finalizeRichContent(container) {
    enhanceCodeBlocks(container);
    if (window.hljs) $$('pre code', container).forEach(block => hljs.highlightElement(block));
    if (window.MathJax?.typesetPromise) MathJax.typesetPromise([container]).catch(() => {});
  }

  function enhanceCodeBlocks(container) {
    $$('pre', container).forEach(pre => {
      if (pre.parentElement?.classList.contains('code-shell')) return;
      const code = $('code', pre);
      const language = [...(code?.classList || [])].find(c => c.startsWith('language-'))?.replace('language-', '') || 'código';
      const shell = document.createElement('div');
      shell.className = 'code-shell';
      const head = document.createElement('div');
      head.className = 'code-head';
      head.innerHTML = `<span>${escapeHtml(language)}</span><button class="code-copy" type="button">Copiar</button>`;
      pre.replaceWith(shell);
      shell.append(head, pre);
      $('button', head).addEventListener('click', async e => {
        await navigator.clipboard.writeText(code?.innerText || pre.innerText);
        e.currentTarget.textContent = 'Copiado';
        setTimeout(() => { e.currentTarget.textContent = 'Copiar'; }, 1400);
      });
    });
  }

  function buildActions(text, meta) {
    const wrap = document.createElement('div');
    wrap.className = 'response-actions';
    const buttons = [
      ['copy', 'Copiar', '<path d="M16 1H4a2 2 0 0 0-2 2v12h2V3h12zm3 4H8a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2zm0 16H8V7h11z"/>'],
      ['up', 'Me gusta', '<path d="M2 21h4V9H2zm20-11a2 2 0 0 0-2-2h-6.31l.95-4.57.03-.32a1.5 1.5 0 0 0-.44-1.06L13.17 1 6.59 7.59A2 2 0 0 0 6 9v10a2 2 0 0 0 2 2h9a2 2 0 0 0 1.84-1.22l3.02-7.05A2 2 0 0 0 22 12z"/>'],
      ['down', 'No me gusta', '<path d="M15 3H6a2 2 0 0 0-1.84 1.22L1.14 11.27A2 2 0 0 0 1 12v2a2 2 0 0 0 2 2h6.31l-.95 4.57-.03.32a1.5 1.5 0 0 0 .44 1.06L9.83 23l6.58-6.59A2 2 0 0 0 17 15V5a2 2 0 0 0-2-2zm4 0v12h4V3z"/>'],
      ['regen', 'Regenerar', '<path d="M17.65 6.35A8 8 0 1 0 20 12h-2a6 6 0 1 1-1.76-4.24L13 11h8V3z"/>']
    ];
    buttons.forEach(([action, title, path]) => {
      const btn = document.createElement('button');
      btn.className = 'action-mini';
      btn.title = title;
      btn.innerHTML = `<svg viewBox="0 0 24 24">${path}</svg>`;
      btn.addEventListener('click', () => handleResponseAction(action, text, meta, btn));
      wrap.appendChild(btn);
    });
    return wrap;
  }

  async function handleResponseAction(action, text, meta, button) {
    if (action === 'copy') {
      await navigator.clipboard.writeText(text);
      toast('Respuesta copiada');
      return;
    }
    if (action === 'regen') {
      if (state.lastPrompt) sendMessage(state.lastPrompt);
      else toast('No hay una instrucción reciente para regenerar');
      return;
    }
    const rating = action === 'up' ? 1 : -1;
    try {
      await apiFetch('/api/feedback', {
        method: 'POST',
        body: JSON.stringify({
          session_id: backendConversationId(), rating,
          prompt: state.lastPrompt || '', response: text, comment: ''
        })
      });
      button.style.color = action === 'up' ? 'var(--green)' : 'var(--red)';
      toast('Gracias por la valoración');
    } catch { toast('No se pudo guardar la valoración'); }
  }

  function persistMessage(message) {
    const chat = currentChat();
    chat.messages.push(message);
    chat.updatedAt = Date.now();
    saveChats();
    renderChatList();
  }

  function updateChatTitle(prompt) {
    const chat = currentChat();
    if (!chat || chat.title !== 'Nueva conversación') return;
    chat.title = prompt.trim().replace(/\s+/g, ' ').slice(0, 46) || 'Conversación';
    chat.updatedAt = Date.now();
    saveChats();
    renderChatList();
  }

  function isNearBottom() {
    return els.chatScroll.scrollHeight - els.chatScroll.scrollTop - els.chatScroll.clientHeight < 140;
  }

  function followBottom() {
    if (state.followOutput) requestAnimationFrame(() => scrollToBottom(false));
    else if (state.isGenerating) els.jumpBtn.classList.add('show');
  }

  function scrollToBottom(smooth) {
    els.chatScroll.scrollTo({ top: els.chatScroll.scrollHeight, behavior: smooth ? 'smooth' : 'auto' });
    state.followOutput = true;
    els.jumpBtn.classList.remove('show');
  }

  function openDrawer() {
    els.drawer.classList.add('open');
    els.backdrop.classList.add('open');
  }

  function closeOverlays() {
    els.drawer.classList.remove('open');
    els.sheet.classList.remove('open');
    els.backdrop.classList.remove('open');
  }

  async function openPanel(panel) {
    closeOverlays();
    els.backdrop.classList.add('open');
    els.sheet.classList.add('open');
    els.sheetTitle.textContent = panelTitle(panel);
    els.sheetBody.innerHTML = '<div class="empty-note">Cargando...</div>';
    try {
      if (panel === 'overview') await renderOverview();
      else if (panel === 'library') await renderLibrary();
      else if (panel === 'memory') await renderMemory();
      else if (panel === 'reminders') await renderReminders();
      else await renderSystem();
    } catch (error) {
      els.sheetBody.innerHTML = `<div class="empty-note">${escapeHtml(error.message || 'No se pudo cargar esta sección.')}</div>`;
    }
  }

  function panelTitle(panel) {
    return ({ overview: 'Centro JARVIS', library: 'Biblioteca', memory: 'Memoria', reminders: 'Recordatorios', system: 'Estado y ajustes' })[panel] || 'JARVIS';
  }

  async function renderOverview() {
    const data = await apiFetch(`/api/dashboard?session_id=${encodeURIComponent(backendConversationId())}`);
    const c = data.counts || {};
    els.sheetBody.innerHTML = `
      <div class="panel-grid">
        ${panelCard('Biblioteca', `${c.documents || 0} documentos`, 'library')}
        ${panelCard('Memoria', `${c.memories || 0} recuerdos`, 'memory')}
        ${panelCard('Recordatorios', `${c.reminders || 0} activos`, 'reminders')}
        ${panelCard('Trabajos', `${c.jobs || 0} registrados`, 'system')}
      </div>
      <div style="height:14px"></div>
      <div class="panel-card"><h3>Estado del núcleo</h3><p>Versión ${escapeHtml(data.version || '6.0.0')} · ${escapeHtml(data.status || 'operativo')} · ${Number(data.usage_24h?.total_tokens || 0).toLocaleString()} tokens en 24 horas.</p></div>`;
    $$('[data-open-panel]', els.sheetBody).forEach(btn => btn.addEventListener('click', () => openPanel(btn.dataset.openPanel)));
  }

  function panelCard(title, text, panel) {
    return `<button class="panel-card" data-open-panel="${panel}" style="text-align:left;color:inherit;cursor:pointer"><h3>${title}</h3><p>${text}</p></button>`;
  }

  async function renderLibrary() {
    const data = await apiFetch(`/api/library?session_id=${encodeURIComponent(backendConversationId())}`);
    const docs = data.documents || [];
    els.sheetBody.innerHTML = `
      <div class="form-row"><button class="primary-btn" id="uploadFromPanel">Subir archivo</button><span style="color:var(--muted);font-size:.8rem">PDF, Word, Excel, PowerPoint, texto y código.</span></div>
      <div style="height:14px"></div>
      <div class="list-stack" id="libraryList">${docs.length ? docs.map(doc => listDocument(doc)).join('') : '<div class="empty-note">Aún no hay documentos en esta conversación.</div>'}</div>`;
    $('#uploadFromPanel', els.sheetBody)?.addEventListener('click', () => els.fileInput.click());
    $$('[data-delete-doc]', els.sheetBody).forEach(btn => btn.addEventListener('click', async () => {
      await apiFetch(`/api/library/${encodeURIComponent(btn.dataset.deleteDoc)}?session_id=${encodeURIComponent(backendConversationId())}`, { method: 'DELETE' });
      renderLibrary();
    }));
  }

  function listDocument(doc) {
    return `<div class="list-item"><div class="list-main"><div class="list-title">${escapeHtml(doc.file_name)}</div><div class="list-sub">${escapeHtml(doc.file_type || '')} · ${Number(doc.characters || 0).toLocaleString()} caracteres</div></div><button class="danger-btn" data-delete-doc="${escapeHtml(doc.id)}">Eliminar</button></div>`;
  }

  async function renderMemory() {
    const data = await apiFetch(`/api/memory?session_id=${encodeURIComponent(backendConversationId())}`);
    const items = data.memories || [];
    els.sheetBody.innerHTML = `
      <div class="form-row"><input class="text-input" id="memoryInput" placeholder="Algo que JARVIS deba recordar..."/><button class="primary-btn" id="saveMemoryBtn">Guardar</button></div>
      <div style="height:14px"></div>
      <div class="list-stack">${items.length ? items.map(item => `<div class="list-item"><div class="list-main"><div class="list-title">${escapeHtml(item.content)}</div><div class="list-sub">${escapeHtml(item.category || 'recuerdo')} · importancia ${item.importance || 3}</div></div><button class="danger-btn" data-delete-memory="${escapeHtml(item.id)}">Eliminar</button></div>`).join('') : '<div class="empty-note">JARVIS todavía no ha guardado recuerdos aquí.</div>'}</div>`;
    $('#saveMemoryBtn', els.sheetBody)?.addEventListener('click', async () => {
      const content = $('#memoryInput', els.sheetBody).value.trim();
      if (!content) return;
      await apiFetch('/api/memory', { method:'POST', body:JSON.stringify({ session_id:backendConversationId(), content, category:'preference', importance:3 }) });
      renderMemory();
    });
    $$('[data-delete-memory]', els.sheetBody).forEach(btn => btn.addEventListener('click', async () => {
      await apiFetch(`/api/memory/${encodeURIComponent(btn.dataset.deleteMemory)}?session_id=${encodeURIComponent(backendConversationId())}`, { method:'DELETE' });
      renderMemory();
    }));
  }

  async function renderReminders() {
    const data = await apiFetch(`/api/reminders?session_id=${encodeURIComponent(backendConversationId())}`);
    const items = data.reminders || [];
    els.sheetBody.innerHTML = `<div class="empty-note">Para crear un recordatorio, escribe en el chat: “Recuérdame mañana a las 8 revisar JARVIS”.</div><div class="list-stack">${items.length ? items.map(item => `<div class="list-item"><div class="list-main"><div class="list-title">${escapeHtml(item.title)}</div><div class="list-sub">${escapeHtml(item.due_at || '')} · ${escapeHtml(item.status || '')}</div></div><button class="danger-btn" data-delete-reminder="${escapeHtml(item.id)}">Cancelar</button></div>`).join('') : ''}</div>`;
    $$('[data-delete-reminder]', els.sheetBody).forEach(btn => btn.addEventListener('click', async () => {
      await apiFetch(`/api/reminders/${encodeURIComponent(btn.dataset.deleteReminder)}?session_id=${encodeURIComponent(backendConversationId())}`, { method:'DELETE' });
      renderReminders();
    }));
  }

  async function renderSystem() {
    const [health, checks] = await Promise.all([apiFetch('/api/health'), apiFetch('/api/self-check')]);
    const configured = health.groq_configured ? 'Configurado' : 'No configurado';
    els.sheetBody.innerHTML = `
      <div class="panel-grid">
        <div class="panel-card"><h3>Núcleo</h3><p>${escapeHtml(health.status || 'desconocido')}</p></div>
        <div class="panel-card"><h3>Modelo</h3><p>${escapeHtml(health.model || '—')}</p></div>
        <div class="panel-card"><h3>Groq</h3><p>${configured}</p></div>
        <div class="panel-card"><h3>Base de datos</h3><p>${health.database_ok ? 'Operativa' : 'Revisar configuración'}</p></div>
      </div>
      <div style="height:14px"></div>
      <div class="panel-card"><h3>Autodiagnóstico</h3><p>${Object.entries(checks.checks || {}).map(([k,v]) => `${escapeHtml(k)}: ${v.ok ? '✓' : '✕'}`).join(' · ')}</p></div>
      <div style="height:14px"></div>
      <div class="panel-card">
        <h3>Conexión avanzada</h3>
        <p>En GitHub Pages, este campo debe contener la URL pública del backend de Render. El valor inicial se toma de static/config.js.</p>
        <div style="height:10px"></div>
        <div class="form-row"><input class="text-input" id="apiBaseInput" placeholder="https://tu-backend.onrender.com" value="${escapeHtml(state.apiBase)}"/><button class="soft-btn" id="saveApiBase">Guardar</button></div>
      </div>`;
    $('#saveApiBase', els.sheetBody)?.addEventListener('click', () => {
      state.apiBase = normalizeBase($('#apiBaseInput', els.sheetBody).value);
      if (state.apiBase) localStorage.setItem(STORE.apiBase, state.apiBase); else localStorage.removeItem(STORE.apiBase);
      toast('Conexión guardada');
      checkHealth({ wake:true });
    });
  }

  async function apiFetch(path, options = {}) {
    const response = await fetch(apiUrl(path), {
      headers: { 'Content-Type':'application/json', ...(options.headers || {}) },
      ...options
    });
    const raw = await response.text();
    let data = {};
    try { data = raw ? JSON.parse(raw) : {}; }
    catch { throw new Error(`Respuesta no válida del servidor (HTTP ${response.status}).`); }
    if (!response.ok) throw new Error(data.detail || data.reply || `Error HTTP ${response.status}`);
    return data;
  }

  async function checkHealth({ wake = false } = {}) {
    if (!navigator.onLine) { setStatus('Sin conexión', 'error'); return; }
    setStatus(wake ? 'Despertando núcleo' : 'Verificando núcleo', 'warning');
    const delays = wake ? [0, 2500, 5000, 8000, 12000, 18000, 25000] : [0];
    state.wakeRetrying = true;
    for (let i = 0; i < delays.length; i++) {
      if (delays[i]) await sleep(delays[i]);
      try {
        const data = await apiFetch('/api/health');
        setStatus(data.status === 'ok' ? 'Núcleo operativo' : 'Modo local activo', data.status === 'ok' ? 'online' : 'warning');
        state.wakeRetrying = false;
        return;
      } catch {
        if (i < delays.length - 1) setStatus(`Despertando núcleo · intento ${i + 2}`, 'warning');
      }
    }
    state.wakeRetrying = false;
    setStatus('Núcleo inaccesible', 'error');
  }

  function setStatus(text, type) {
    els.statusText.textContent = text;
    els.statusPill.classList.remove('online', 'error');
    if (type === 'online') els.statusPill.classList.add('online');
    if (type === 'error') els.statusPill.classList.add('error');
  }

  async function pollNotifications() {
    setInterval(async () => {
      try {
        const data = await apiFetch(`/api/notifications?session_id=${encodeURIComponent(backendConversationId())}`);
        (data.notifications || []).forEach(item => toast(`Recordatorio: ${item.title}`));
      } catch { /* notificaciones son secundarias */ }
    }, 60000);
  }

  function startVoiceInput() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) { toast('El dictado no está disponible en este navegador'); return; }
    const recognition = new SpeechRecognition();
    recognition.lang = 'es-HN';
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    recognition.onstart = () => toast('Escuchando...');
    recognition.onerror = () => toast('No se pudo usar el micrófono');
    recognition.onresult = e => {
      els.userInput.value = e.results[0][0].transcript || '';
      saveDraft(); autoResize(); els.userInput.focus();
    };
    recognition.start();
  }

  function humanToolName(name) {
    return ({ web_search:'Búsqueda web', calculator:'Calculadora', sympy_solve:'Matemática', memory_save:'Memoria guardada', memory_search:'Memoria consultada', memory_delete:'Memoria eliminada', reminder_create:'Recordatorio', reminder_list:'Recordatorios', reminder_cancel:'Recordatorio cancelado', document_search:'Biblioteca' })[name] || name.replaceAll('_',' ');
  }

  function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>'"]/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', "'":'&#39;', '"':'&quot;' })[c]);
  }

  function toast(message) {
    els.toast.textContent = message;
    els.toast.classList.add('show');
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => els.toast.classList.remove('show'), 2500);
  }

  function sleep(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }
})();
