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
    projectBtn: $('#projectBtn'),
    projectName: $('#projectName'),
    commandBtn: $('#commandBtn'),
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
    quickNewProjectBtn: $('#quickNewProjectBtn'),
    projectList: $('#projectList'),
    drawerSearch: $('#drawerSearch'),
    chatList: $('#chatList'),
    sheet: $('#sheet'),
    sheetTitle: $('#sheetTitle'),
    sheetBody: $('#sheetBody'),
    closeSheetBtn: $('#closeSheetBtn'),
    toast: $('#toast'),
    reactorFx: $('#reactorFx'),
    commandPalette: $('#commandPalette'),
    commandInput: $('#commandInput'),
    commandResults: $('#commandResults'),
    offlineBanner: $('#offlineBanner')
  };

  const STORE = {
    client: 'jarvis_nexus_client',
    chats: 'jarvis_nexus_chats',
    active: 'jarvis_nexus_active_chat',
    draftPrefix: 'jarvis_nexus_draft_',
    apiBase: 'jarvis_pages_api_base_v11',
    mode: 'jarvis_nexus_mode',
    projects: 'jarvis_nexus_projects_v11',
    activeProject: 'jarvis_nexus_active_project_v11'
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
    projects: loadJSON(STORE.projects, {}),
    activeProjectId: localStorage.getItem(STORE.activeProject) || '',
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
    wakeRetrying: false,
    commandIndex: 0,
    commandItems: []
  };

  localStorage.setItem(STORE.client, state.clientId);

  document.addEventListener('DOMContentLoaded', init);

  function init() {
    document.title = window.JARVIS_CONFIG?.APP_NAME || 'J.A.R.V.I.S. — Multi-Provider Core';
    ensureProjects();
    migrateChatsToProjects();
    if (!state.activeChatId || !state.chats[state.activeChatId] || currentChat()?.projectId !== state.activeProjectId) {
      state.activeChatId = latestChatForProject(state.activeProjectId)?.id || '';
    }
    if (!state.activeChatId) createChat(false);
    configureMarkdown();
    bindEvents();
    renderMode();
    renderProjectSwitcher();
    renderProjectList();
    renderChatList();
    renderActiveChat();
    restoreDraft();
    autoResize();
    bindHeroFx();
    checkHealth({ wake: true });
    pollNotifications();
    registerServiceWorker();
    updateOfflineBanner();
    requestAnimationFrame(() => document.body.classList.add('app-ready'));
  }

  function bindEvents() {
    els.menuBtn.addEventListener('click', openDrawer);
    els.closeDrawerBtn.addEventListener('click', closeOverlays);
    els.backdrop.addEventListener('click', closeOverlays);
    els.workspaceBtn.addEventListener('click', () => openPanel('overview'));
    els.projectBtn?.addEventListener('click', () => openPanel('projects'));
    els.commandBtn?.addEventListener('click', openCommandPalette);
    els.closeSheetBtn.addEventListener('click', closeOverlays);
    els.newChatTopBtn.addEventListener('click', () => createChat(true));
    els.newChatBtn.addEventListener('click', () => createChat(true));
    els.quickNewProjectBtn?.addEventListener('click', createProjectFlow);
    els.drawerSearch?.addEventListener('input', () => renderChatList(els.drawerSearch.value));

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
    els.statusPill.addEventListener('click', () => openPanel('system'));
    els.reactorFx?.addEventListener('click', activateCoreVisual);
    els.commandPalette?.addEventListener('click', event => { if (event.target === els.commandPalette) closeCommandPalette(); });
    els.commandInput?.addEventListener('input', renderCommandPalette);
    els.commandInput?.addEventListener('keydown', handleCommandKeydown);

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

    window.addEventListener('online', () => { updateOfflineBanner(); checkHealth({ wake: true }); });
    window.addEventListener('offline', () => { updateOfflineBanner(); setStatus('Sin conexión', 'error'); });
    window.addEventListener('keydown', handleGlobalKeys);
  }


  function activateCoreVisual() {
    const node = els.reactorFx;
    if (!node) return;
    node.classList.remove('core-surge');
    void node.offsetWidth;
    node.classList.add('core-surge');
    els.ambient.classList.add('active');
    clearTimeout(activateCoreVisual.timer);
    activateCoreVisual.timer = setTimeout(() => {
      node.classList.remove('core-surge');
      if (!state.isGenerating) els.ambient.classList.remove('active');
    }, 980);
    toast('Núcleo visual sincronizado');
    setTimeout(() => els.userInput.focus(), 180);
  }

  function handleGlobalKeys(event) {
    const key = event.key.toLowerCase();
    if (event.key === 'Escape') {
      closeCommandPalette();
      closeOverlays();
    }
    if ((event.ctrlKey || event.metaKey) && key === 'k') {
      event.preventDefault();
      openCommandPalette();
      return;
    }
    if ((event.ctrlKey || event.metaKey) && event.shiftKey && key === 'n') {
      event.preventDefault();
      createChat(true);
      return;
    }
    if ((event.ctrlKey || event.metaKey) && key === 'e') {
      event.preventDefault();
      openPanel('export');
      return;
    }
    if (event.key === '/' && !event.metaKey && !event.ctrlKey && !event.altKey) {
      const tag = document.activeElement?.tagName?.toLowerCase();
      if (tag !== 'textarea' && tag !== 'input') {
        event.preventDefault();
        els.userInput.focus();
      }
    }
  }

  function bindHeroFx() {
    const node = els.reactorFx;
    if (!node || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const update = (x, y) => {
      node.style.setProperty('--mx', `${x}px`);
      node.style.setProperty('--my', `${y}px`);
      const rx = ((y / node.clientHeight) - 0.5) * -8;
      const ry = ((x / node.clientWidth) - 0.5) * 10;
      node.style.setProperty('--rx', `${rx.toFixed(2)}deg`);
      node.style.setProperty('--ry', `${ry.toFixed(2)}deg`);
    };
    node.addEventListener('pointermove', (event) => {
      const rect = node.getBoundingClientRect();
      update(event.clientX - rect.left, event.clientY - rect.top);
    });
    node.addEventListener('pointerleave', () => {
      node.style.setProperty('--mx', `${node.clientWidth / 2}px`);
      node.style.setProperty('--my', `${node.clientHeight / 2}px`);
      node.style.setProperty('--rx', '0deg');
      node.style.setProperty('--ry', '0deg');
    });
    node.style.setProperty('--mx', `${node.clientWidth / 2}px`);
    node.style.setProperty('--my', `${node.clientHeight / 2}px`);
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

  function saveProjects() {
    localStorage.setItem(STORE.projects, JSON.stringify(state.projects));
    localStorage.setItem(STORE.activeProject, state.activeProjectId);
  }

  function ensureProjects() {
    const projects = Object.values(state.projects || {});
    if (!projects.length) {
      const id = 'project_general';
      state.projects = {
        [id]: {
          id,
          name: 'General',
          description: 'Conversaciones y tareas generales.',
          createdAt: Date.now(),
          updatedAt: Date.now()
        }
      };
      state.activeProjectId = id;
      saveProjects();
      return;
    }
    if (!state.activeProjectId || !state.projects[state.activeProjectId]) {
      state.activeProjectId = projects[0].id;
      saveProjects();
    }
  }

  function migrateChatsToProjects() {
    let changed = false;
    Object.values(state.chats).forEach(chat => {
      if (!chat.projectId) {
        chat.projectId = state.activeProjectId;
        changed = true;
      }
    });
    if (changed) saveChats();
  }

  function currentProject() {
    return state.projects[state.activeProjectId] || Object.values(state.projects)[0];
  }

  function latestChatForProject(projectId) {
    return Object.values(state.chats)
      .filter(chat => chat.projectId === projectId)
      .sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0))[0] || null;
  }

  function projectChatCount(projectId) {
    return Object.values(state.chats).filter(chat => chat.projectId === projectId).length;
  }

  function renderProjectSwitcher() {
    const project = currentProject();
    if (els.projectName) els.projectName.textContent = project?.name || 'General';
  }

  function renderProjectList() {
    if (!els.projectList) return;
    const projects = Object.values(state.projects).sort((a,b) => (b.updatedAt || 0) - (a.updatedAt || 0));
    els.projectList.innerHTML = '';
    projects.forEach(project => {
      const button = document.createElement('button');
      button.className = `project-item${project.id === state.activeProjectId ? ' active' : ''}`;
      button.innerHTML = `<span class="project-item-dot"></span><span class="project-item-copy"><span class="project-item-name">${escapeHtml(project.name)}</span><span class="project-item-count">${projectChatCount(project.id)} conversaciones</span></span>`;
      button.addEventListener('click', () => switchProject(project.id));
      els.projectList.appendChild(button);
    });
  }

  function createProjectFlow() {
    const name = prompt('Nombre del nuevo proyecto:');
    if (!name?.trim()) return;
    const description = prompt('Descripción breve del proyecto:', '') || '';
    const id = uid('project');
    state.projects[id] = {
      id,
      name: name.trim().slice(0, 60),
      description: description.trim().slice(0, 240),
      createdAt: Date.now(),
      updatedAt: Date.now()
    };
    state.activeProjectId = id;
    saveProjects();
    renderProjectSwitcher();
    renderProjectList();
    createChat(false);
    toast(`Proyecto “${state.projects[id].name}” creado`);
  }

  function switchProject(projectId) {
    if (!state.projects[projectId] || projectId === state.activeProjectId) {
      closeOverlays();
      return;
    }
    if (state.isGenerating) stopGeneration();
    state.activeProjectId = projectId;
    state.projects[projectId].updatedAt = Date.now();
    const latest = latestChatForProject(projectId);
    state.activeChatId = latest?.id || '';
    saveProjects();
    if (!state.activeChatId) createChat(false);
    saveChats();
    renderProjectSwitcher();
    renderProjectList();
    renderChatList();
    renderActiveChat();
    restoreDraft();
    closeOverlays();
    toast(`Proyecto activo: ${currentProject()?.name || 'General'}`);
  }

  function deleteProject(projectId) {
    if (!state.projects[projectId]) return;
    if (Object.keys(state.projects).length <= 1) {
      toast('Debe existir al menos un proyecto');
      return;
    }
    const project = state.projects[projectId];
    if (!confirm(`¿Eliminar el proyecto “${project.name}” y sus conversaciones locales?`)) return;
    Object.keys(state.chats).forEach(chatId => {
      if (state.chats[chatId].projectId === projectId) {
        delete state.chats[chatId];
        localStorage.removeItem(STORE.draftPrefix + chatId);
      }
    });
    delete state.projects[projectId];
    state.activeProjectId = Object.keys(state.projects)[0];
    state.activeChatId = latestChatForProject(state.activeProjectId)?.id || '';
    saveProjects();
    saveChats();
    if (!state.activeChatId) createChat(false);
    renderProjectSwitcher();
    renderProjectList();
    renderChatList();
    renderActiveChat();
  }

  function saveChats() {
    localStorage.setItem(STORE.chats, JSON.stringify(state.chats));
    localStorage.setItem(STORE.active, state.activeChatId);
  }

  function currentChat() {
    return state.chats[state.activeChatId];
  }

  function backendConversationId(chatId = state.activeChatId) {
    const projectId = currentChat()?.projectId || state.activeProjectId || 'project_general';
    return `public_${state.clientId}_${projectId}_${chatId}`.replace(/[^a-zA-Z0-9_.:@-]/g, '_').slice(0, 150);
  }

  function createChat(showToast = true) {
    if (state.isGenerating) stopGeneration();
    const id = uid('chat');
    state.chats[id] = { id, projectId: state.activeProjectId, title: 'Nueva conversación', messages: [], createdAt: Date.now(), updatedAt: Date.now() };
    state.activeChatId = id;
    if (state.projects[state.activeProjectId]) state.projects[state.activeProjectId].updatedAt = Date.now();
    saveProjects();
    saveChats();
    renderProjectList();
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
    const remaining = Object.values(state.chats).filter(chat => chat.projectId === state.activeProjectId);
    state.activeChatId = remaining[0]?.id || '';
    if (!state.activeChatId) createChat(false);
    saveChats();
    renderProjectList();
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

  function renderChatList(query = '') {
    const normalized = String(query || '').trim().toLowerCase();
    const items = Object.values(state.chats)
      .filter(chat => chat.projectId === state.activeProjectId)
      .filter(chat => !normalized || `${chat.title || ''} ${(chat.messages || []).map(item => item.content || '').join(' ')}`.toLowerCase().includes(normalized))
      .sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0));
    els.chatList.innerHTML = '';
    if (!items.length) {
      els.chatList.innerHTML = '<div class="history-empty"><span>◇</span><strong>Sin conversaciones</strong><small>Inicia un chat nuevo dentro de este proyecto.</small></div>';
      return;
    }
    items.forEach(chat => {
      const btn = document.createElement('button');
      const preview = chatPreview(chat);
      const count = chat.messages?.length || 0;
      btn.className = `chat-item${chat.id === state.activeChatId ? ' active' : ''}`;
      btn.title = chat.title || 'Conversación';
      btn.innerHTML = `
        <span class="chat-item-icon" aria-hidden="true">${chat.id === state.activeChatId ? '◆' : '◇'}</span>
        <span class="chat-item-copy">
          <span class="chat-item-title">${escapeHtml(chat.title || 'Conversación')}</span>
          <span class="chat-item-preview">${escapeHtml(preview)}</span>
          <span class="chat-item-meta">${count} ${count === 1 ? 'mensaje' : 'mensajes'} · ${escapeHtml(formatRelativeTime(chat.updatedAt))}</span>
        </span>
        <span class="chat-item-delete" role="button" aria-label="Eliminar conversación" title="Eliminar">×</span>`;
      btn.addEventListener('click', event => {
        if (event.target.closest('.chat-item-delete')) {
          event.stopPropagation();
          if (confirm('¿Eliminar esta conversación?')) removeChat(chat.id);
          return;
        }
        switchChat(chat.id);
      });
      btn.addEventListener('contextmenu', e => {
        e.preventDefault();
        if (confirm('¿Eliminar esta conversación?')) removeChat(chat.id);
      });
      els.chatList.appendChild(btn);
    });
  }

  function chatPreview(chat) {
    const latest = [...(chat.messages || [])].reverse().find(item => String(item.content || '').trim());
    return String(latest?.content || 'Conversación nueva').replace(/\s+/g, ' ').slice(0, 82);
  }

  function formatRelativeTime(value) {
    const time = Number(value || 0);
    if (!time) return 'ahora';
    const diff = Date.now() - time;
    const minute = 60 * 1000;
    const hour = 60 * minute;
    const day = 24 * hour;
    if (diff < minute) return 'ahora';
    if (diff < hour) return `hace ${Math.max(1, Math.floor(diff / minute))} min`;
    if (diff < day) return `hace ${Math.max(1, Math.floor(diff / hour))} h`;
    if (diff < 7 * day) return `hace ${Math.max(1, Math.floor(diff / day))} d`;
    return new Date(time).toLocaleDateString('es-HN', { day: '2-digit', month: 'short' });
  }

  function showWelcome() {
    clearTimeout(showWelcome.timer);
    els.welcome.classList.remove('hidden', 'leaving');
    els.welcome.style.display = 'flex';
  }

  function dismissWelcome(animated = true) {
    clearTimeout(showWelcome.timer);
    if (els.welcome.classList.contains('hidden')) return;
    if (!animated || window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      els.welcome.classList.add('hidden');
      els.welcome.classList.remove('leaving');
      els.welcome.style.display = 'none';
      return;
    }
    els.welcome.classList.add('leaving');
    showWelcome.timer = setTimeout(() => {
      els.welcome.classList.add('hidden');
      els.welcome.classList.remove('leaving');
      els.welcome.style.display = 'none';
    }, 280);
  }

  function renderActiveChat() {
    els.messages.innerHTML = '';
    const chat = currentChat();
    const hasMessages = Boolean(chat?.messages?.length);
    if (!hasMessages) {
      showWelcome();
      return;
    }
    dismissWelcome(false);
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
    dismissWelcome(true);

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
      const clientRequestId = createRequestId();
      const payload = {
        message: text || 'Analiza los archivos adjuntos.',
        session_id: backendConversationId(),
        project_name: currentProject()?.name || 'General',
        mode: state.mode,
        files: outgoingFiles,
        request_id: clientRequestId
      };
      const data = await requestJarvis(payload, state.abortController.signal);

      hideThinking();
      const reply = data.reply || data.response || 'El núcleo no devolvió contenido.';
      const meta = {
        tools: data.tools || [],
        model: data.model || '',
        cached: Boolean(data.cached),
        degraded: Boolean(data.degraded),
        mode: data.mode || '',
        intent: data.intent || '',
        route: data.route || '',
        latencyMs: Number(data.latency_ms || 0),
        requestId: data.request_id || '',
        verified: Boolean(data.verified),
        verification: data.verification || {},
        resolutionAttempts: Number(data.resolution_attempts || 0),
        resolutionTrace: Array.isArray(data.resolution_trace) ? data.resolution_trace : [],
        recoveredErrors: Array.isArray(data.recovered_errors) ? data.recovered_errors : [],
        recovered: Boolean(data.recovered),
        similarCache: Boolean(data.similar_cache),
        idempotentReplay: Boolean(data.idempotent_replay)
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
      ? ['Preparando investigación', 'Probando rutas de búsqueda', 'Revisando y depurando fuentes', 'Comparando resultados', 'Verificando la respuesta']
      : ['Preparando respuesta', 'Analizando contexto', 'Seleccionando la mejor ruta', 'Probando alternativas si es necesario', 'Verificando el resultado'];
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
    const avatarWrap = document.createElement('div');
    avatarWrap.className = 'assistant-avatar';
    const avatar = document.createElement('img');
    const reactorRef = document.querySelector('.brand-reactor')?.getAttribute('src') || './static/jarvis-reactor-v18.png';
    avatar.src = new URL(reactorRef, document.baseURI).href;
    avatar.alt = 'JARVIS';
    avatarWrap.appendChild(avatar);

    const body = document.createElement('div');
    body.className = 'assistant-body';
    const head = document.createElement('div');
    head.className = 'assistant-head';
    const modelName = formatModelName(meta.model);
    head.innerHTML = `<span class="assistant-label">J.A.R.V.I.S.</span><span class="assistant-head-meta">${escapeHtml(modelName || humanRoute(meta.route) || 'Núcleo inteligente')}</span>`;

    const content = document.createElement('div');
    content.className = 'assistant-content';
    body.append(head, content);

    const grid = document.createElement('div');
    grid.className = 'assistant-row';
    grid.append(avatarWrap, body);
    row.appendChild(grid);
    els.messages.appendChild(row);

    const html = renderMarkdown(text);
    if (animateBlocks && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) revealHtmlBlocks(content, html);
    else {
      content.innerHTML = html;
      finalizeRichContent(content);
    }

    const tools = Array.isArray(meta.tools) ? meta.tools : [];
    if (tools.length || meta.cached || meta.degraded || meta.intent || meta.route || meta.latencyMs) {
      const toolRow = document.createElement('div');
      toolRow.className = 'tool-row';
      tools.forEach(tool => {
        const name = typeof tool === 'string' ? tool : (tool.name || tool.tool || 'Herramienta');
        toolRow.insertAdjacentHTML('beforeend', `<span class="tool-chip">${escapeHtml(humanToolName(name))}</span>`);
      });
      if (meta.intent) toolRow.insertAdjacentHTML('beforeend', `<span class="tool-chip intent-chip">${escapeHtml(humanIntent(meta.intent))}</span>`);
      if (meta.route) toolRow.insertAdjacentHTML('beforeend', `<span class="tool-chip route-chip">${escapeHtml(humanRoute(meta.route))}</span>`);
      if (meta.latencyMs) toolRow.insertAdjacentHTML('beforeend', `<span class="tool-chip latency-chip">${Math.max(1, Math.round(meta.latencyMs))} ms</span>`);
      if (meta.cached) toolRow.insertAdjacentHTML('beforeend', '<span class="tool-chip">Respuesta en caché</span>');
      if (meta.similarCache) toolRow.insertAdjacentHTML('beforeend', '<span class="tool-chip">Caché similar</span>');
      if (meta.degraded) toolRow.insertAdjacentHTML('beforeend', '<span class="tool-chip">Modo resistente</span>');
      if (meta.verified) toolRow.insertAdjacentHTML('beforeend', '<span class="tool-chip verified-chip">Verificado</span>');
      if (meta.resolutionAttempts > 1) toolRow.insertAdjacentHTML('beforeend', `<span class="tool-chip attempts-chip">${meta.resolutionAttempts} rutas probadas</span>`);
      if (meta.recoveredErrors?.length || meta.recovered) toolRow.insertAdjacentHTML('beforeend', '<span class="tool-chip recovered-chip">Recuperado automáticamente</span>');
      if (meta.idempotentReplay) toolRow.insertAdjacentHTML('beforeend', '<span class="tool-chip">Reintento seguro</span>');
      body.appendChild(toolRow);
    }

    const actions = buildActions(text, meta);
    body.appendChild(actions);
    requestAnimationFrame(() => actions.classList.add('visible'));

    if (scroll) followBottom();
  }

  function formatModelName(model) {
    const value = String(model || '').trim();
    if (!value) return '';
    return value
      .replace(/^meta-llama\//i, '')
      .replace(/^openai\//i, '')
      .replace(/[-_]+/g, ' ')
      .replace(/\b\w/g, char => char.toUpperCase())
      .slice(0, 42);
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
    if (state.projects[chat.projectId]) state.projects[chat.projectId].updatedAt = chat.updatedAt;
    saveProjects();
    saveChats();
    renderProjectList();
    renderChatList(els.drawerSearch?.value || '');
  }

  function updateChatTitle(prompt) {
    const chat = currentChat();
    if (!chat || chat.title !== 'Nueva conversación') return;
    chat.title = prompt.trim().replace(/\s+/g, ' ').slice(0, 46) || 'Conversación';
    chat.updatedAt = Date.now();
    saveChats();
    renderProjectList();
    renderChatList(els.drawerSearch?.value || '');
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

  function commandDefinitions() {
    return [
      { id:'new-chat', icon:'＋', title:'Nueva conversación', sub:'Crear un chat en el proyecto activo', shortcut:'Ctrl+Shift+N', run:() => createChat(true) },
      { id:'new-project', icon:'◆', title:'Nuevo proyecto', sub:'Crear un espacio de trabajo independiente', run:createProjectFlow },
      { id:'projects', icon:'◇', title:'Administrar proyectos', sub:'Cambiar, crear o eliminar proyectos', run:() => openPanel('projects') },
      { id:'library', icon:'▣', title:'Abrir biblioteca', sub:'Documentos del proyecto activo', run:() => openPanel('library') },
      { id:'memory', icon:'◈', title:'Abrir memoria', sub:'Recuerdos y preferencias del proyecto', run:() => openPanel('memory') },
      { id:'jobs', icon:'◉', title:'Trabajos autónomos', sub:'Crear y revisar tareas en segundo plano', run:() => openPanel('jobs') },
      { id:'search', icon:'⌕', title:'Buscar conocimiento', sub:'Memoria, documentos y conversaciones', run:() => openPanel('search') },
      { id:'export', icon:'⇩', title:'Exportar conversación', sub:'Descargar Markdown o JSON', shortcut:'Ctrl+E', run:() => openPanel('export') },
      { id:'providers', icon:'◫', title:'Proveedores IA', sub:'OpenAI, Gemini, Groq, Ollama y rutas automáticas', run:() => openPanel('providers') },
      { id:'resilience', icon:'⟲', title:'Resiliencia y rutas', sub:'Proveedores, verificaciones y recuperaciones', run:() => openPanel('resilience') },
      { id:'performance', icon:'⌁', title:'Rendimiento', sub:'Velocidad, caché, circuitos y trabajos', run:() => openPanel('performance') },
      { id:'system', icon:'⚙', title:'Estado del núcleo', sub:'Diagnóstico, modelos y conexión', run:() => openPanel('system') },
      { id:'focus', icon:'/', title:'Escribir una pregunta', sub:'Enfocar el campo de conversación', shortcut:'/', run:() => els.userInput.focus() },
      { id:'mode', icon:'◎', title:'Cambiar modo', sub:MODES.find(item => item.id === state.mode)?.label || 'Modo automático', run:cycleMode },
    ];
  }

  function openCommandPalette() {
    closeOverlays();
    els.commandPalette?.classList.add('open');
    state.commandIndex = 0;
    if (els.commandInput) els.commandInput.value = '';
    renderCommandPalette();
    setTimeout(() => els.commandInput?.focus(), 40);
  }

  function closeCommandPalette() {
    els.commandPalette?.classList.remove('open');
  }

  function paletteItems(query = '') {
    const needle = query.trim().toLowerCase();
    const commands = commandDefinitions()
      .filter(item => !needle || `${item.title} ${item.sub}`.toLowerCase().includes(needle))
      .map(item => ({ ...item, group:'Comandos' }));
    const projects = Object.values(state.projects)
      .filter(item => !needle || `${item.name} ${item.description || ''}`.toLowerCase().includes(needle))
      .slice(0,8)
      .map(item => ({ id:`project:${item.id}`, icon:'◆', title:item.name, sub:item.description || 'Cambiar a este proyecto', group:'Proyectos', run:() => switchProject(item.id) }));
    const chats = Object.values(state.chats)
      .filter(chat => !needle || `${chat.title} ${(chat.messages || []).map(item => item.content || '').join(' ')}`.toLowerCase().includes(needle))
      .sort((a,b) => (b.updatedAt || 0) - (a.updatedAt || 0))
      .slice(0,10)
      .map(chat => ({ id:`chat:${chat.id}`, icon:'◌', title:chat.title || 'Conversación', sub:state.projects[chat.projectId]?.name || 'Proyecto', group:'Conversaciones', run:() => { if (chat.projectId !== state.activeProjectId) switchProject(chat.projectId); switchChat(chat.id); } }));
    return [...commands, ...projects, ...chats];
  }

  function renderCommandPalette() {
    if (!els.commandResults) return;
    const items = paletteItems(els.commandInput?.value || '');
    state.commandItems = items;
    state.commandIndex = Math.max(0, Math.min(state.commandIndex, items.length - 1));
    if (!items.length) {
      els.commandResults.innerHTML = '<div class="empty-note">No hay coincidencias.</div>';
      return;
    }
    let currentGroup = '';
    els.commandResults.innerHTML = items.map((item,index) => {
      const group = item.group !== currentGroup ? `<div class="command-group-label">${escapeHtml(item.group)}</div>` : '';
      currentGroup = item.group;
      return `${group}<button class="command-item${index === state.commandIndex ? ' active' : ''}" data-command-index="${index}"><span class="command-item-icon">${escapeHtml(item.icon)}</span><span class="command-item-copy"><span class="command-item-title">${escapeHtml(item.title)}</span><span class="command-item-sub">${escapeHtml(item.sub || '')}</span></span>${item.shortcut ? `<span class="command-item-shortcut">${escapeHtml(item.shortcut)}</span>` : ''}</button>`;
    }).join('');
    $$('[data-command-index]', els.commandResults).forEach(button => button.addEventListener('click', () => runCommand(Number(button.dataset.commandIndex))));
  }

  function handleCommandKeydown(event) {
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      state.commandIndex = Math.min(state.commandIndex + 1, state.commandItems.length - 1);
      renderCommandPalette();
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      state.commandIndex = Math.max(state.commandIndex - 1, 0);
      renderCommandPalette();
    } else if (event.key === 'Enter') {
      event.preventDefault();
      runCommand(state.commandIndex);
    } else if (event.key === 'Escape') {
      closeCommandPalette();
    }
  }

  function runCommand(index) {
    const item = state.commandItems[index];
    if (!item) return;
    closeCommandPalette();
    item.run?.();
  }

  function openDrawer() {
    renderProjectList();
    renderChatList(els.drawerSearch?.value || '');
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
      else if (panel === 'projects') await renderProjects();
      else if (panel === 'library') await renderLibrary();
      else if (panel === 'memory') await renderMemory();
      else if (panel === 'reminders') await renderReminders();
      else if (panel === 'jobs') await renderJobs();
      else if (panel === 'search') await renderKnowledgeSearch();
      else if (panel === 'export') await renderExport();
      else if (panel === 'providers') await renderProviders();
      else if (panel === 'resilience') await renderResilience();
      else if (panel === 'performance') await renderPerformance();
      else await renderSystem();
    } catch (error) {
      els.sheetBody.innerHTML = `<div class="empty-note">${escapeHtml(error.message || 'No se pudo cargar esta sección.')}</div>`;
    }
  }

  function panelTitle(panel) {
    return ({ overview: 'Centro JARVIS', projects: 'Proyectos', library: 'Biblioteca', memory: 'Memoria', reminders: 'Recordatorios', jobs: 'Trabajos autónomos', search: 'Buscar conocimiento', export: 'Exportar conversación', providers: 'Proveedores IA', resilience: 'Resiliencia y rutas', performance: 'Rendimiento y estabilidad', system: 'Estado y ajustes' })[panel] || 'JARVIS';
  }

  async function renderOverview() {
    const data = await apiFetch(`/api/dashboard?session_id=${encodeURIComponent(backendConversationId())}`);
    const c = data.counts || {};
    els.sheetBody.innerHTML = `
      <div class="panel-grid">
        ${panelCard('Proyecto activo', escapeHtml(currentProject()?.name || 'General'), 'projects')}
        ${panelCard('Biblioteca', `${c.documents || 0} documentos`, 'library')}
        ${panelCard('Memoria', `${c.memories || 0} recuerdos`, 'memory')}
        ${panelCard('Trabajos', `${c.jobs || 0} registrados`, 'jobs')}
      </div>
      <div style="height:14px"></div>
      <div class="panel-card"><h3>Estado del núcleo</h3><p>Versión ${escapeHtml(data.version || '19.0.0')} · ${escapeHtml(data.status || 'operativo')} · ${Number(data.usage_24h?.total_tokens || 0).toLocaleString()} tokens en 24 horas.</p></div>`;
    $$('[data-open-panel]', els.sheetBody).forEach(btn => btn.addEventListener('click', () => openPanel(btn.dataset.openPanel)));
  }

  function panelCard(title, text, panel) {
    return `<button class="panel-card" data-open-panel="${panel}" style="text-align:left;color:inherit;cursor:pointer"><h3>${title}</h3><p>${text}</p></button>`;
  }

  async function renderProjects() {
    const projects = Object.values(state.projects).sort((a,b) => (b.updatedAt || 0) - (a.updatedAt || 0));
    els.sheetBody.innerHTML = `
      <div class="project-hero premium-project-hero">
        <div class="project-hero-icon">◈</div>
        <div><h3>Espacios de trabajo</h3><p>Cada proyecto separa conversaciones, memoria, documentos, recordatorios y trabajos del núcleo.</p></div>
      </div>
      <div class="project-create-box">
        <input class="text-input" id="projectNameInput" placeholder="Nombre del proyecto"/>
        <input class="text-input" id="projectDescInput" placeholder="Descripción breve"/>
        <button class="primary-btn" id="createProjectPanelBtn">Crear proyecto</button>
      </div>
      <div class="project-grid premium-project-grid">${projects.map(project => {
        const chats = Object.values(state.chats).filter(chat => chat.projectId === project.id);
        const messages = chats.reduce((total, chat) => total + (chat.messages?.length || 0), 0);
        const active = project.id === state.activeProjectId;
        return `
          <article class="project-card${active ? ' active' : ''}" data-project-card="${escapeHtml(project.id)}">
            <div class="project-card-top">
              <span class="project-card-orb">${active ? '◆' : '◇'}</span>
              ${active ? '<span class="project-active-badge">Activo</span>' : ''}
              ${projects.length > 1 ? `<button class="project-card-delete" data-delete-project="${escapeHtml(project.id)}" title="Eliminar">×</button>` : ''}
            </div>
            <h3>${escapeHtml(project.name)}</h3>
            <p>${escapeHtml(project.description || 'Sin descripción.')}</p>
            <div class="project-stats">
              <span><strong>${chats.length}</strong> chats</span>
              <span><strong>${messages}</strong> mensajes</span>
              <span>${escapeHtml(formatRelativeTime(project.updatedAt))}</span>
            </div>
          </article>`;
      }).join('')}</div>`;
    $('#createProjectPanelBtn', els.sheetBody)?.addEventListener('click', () => {
      const name = $('#projectNameInput', els.sheetBody).value.trim();
      if (!name) return;
      const desc = $('#projectDescInput', els.sheetBody).value.trim();
      const id = uid('project');
      state.projects[id] = { id, name:name.slice(0,60), description:desc.slice(0,240), createdAt:Date.now(), updatedAt:Date.now() };
      state.activeProjectId = id;
      saveProjects();
      renderProjectSwitcher();
      renderProjectList();
      createChat(false);
      renderProjects();
    });
    $$('[data-project-card]', els.sheetBody).forEach(card => card.addEventListener('click', event => {
      if (event.target.closest('[data-delete-project]')) return;
      switchProject(card.dataset.projectCard);
    }));
    $$('[data-delete-project]', els.sheetBody).forEach(btn => btn.addEventListener('click', event => {
      event.stopPropagation();
      deleteProject(btn.dataset.deleteProject);
      renderProjects();
    }));
  }

  async function renderJobs() {
    const data = await apiFetch(`/api/jobs?session_id=${encodeURIComponent(backendConversationId())}`);
    const jobs = data.jobs || [];
    const workerCount = Number(data.workers || 0);
    els.sheetBody.innerHTML = `
      <div class="jobs-hero">
        <div class="jobs-hero-icon">◉</div>
        <div><h3>Trabajos persistentes</h3><p>${workerCount || '—'} worker(s) disponibles. Los trabajos guardan intentos, checkpoints y pueden pausarse, reanudarse o recuperarse.</p></div>
      </div>
      <div class="form-row"><input class="text-input" id="jobTitleInput" placeholder="Nombre del trabajo"/><input class="text-input" id="jobPromptInput" placeholder="Instrucción que JARVIS ejecutará"/><button class="primary-btn" id="createJobBtn">Ejecutar</button></div>
      <div style="height:14px"></div>
      <div class="list-stack">${jobs.length ? jobs.map(job => {
        const status = String(job.status || 'queued');
        const progress = Math.max(0,Math.min(100,Number(job.progress || 0)));
        const canPause = ['queued','running','retrying'].includes(status);
        const canResume = ['paused'].includes(status);
        const canCancel = ['queued','running','retrying','paused','cancelling'].includes(status);
        const canRetry = ['failed','cancelled'].includes(status);
        return `<article class="job-card status-${escapeHtml(status)}">
          <div class="job-card-head"><div><div class="list-title">${escapeHtml(job.title)}</div><div class="list-sub">${escapeHtml(status)} · ${progress}% · intento ${Number(job.attempt || 0)}/${Number(job.max_attempts || 0)}</div></div><span class="job-state">${escapeHtml(status)}</span></div>
          <div class="job-progress"><span style="width:${progress}%"></span></div>
          <div class="job-checkpoint">${escapeHtml(job.checkpoint || 'Esperando ejecución')}</div>
          ${job.error ? `<div class="job-error">${escapeHtml(String(job.error).slice(0,300))}</div>` : ''}
          ${job.result ? `<div class="job-result">${escapeHtml(String(job.result).slice(0,420))}</div>` : ''}
          <div class="job-actions">
            ${canPause ? `<button class="soft-btn" data-job-action="pause" data-job-id="${escapeHtml(job.id)}">Pausar</button>` : ''}
            ${canResume ? `<button class="primary-btn" data-job-action="resume" data-job-id="${escapeHtml(job.id)}">Reanudar</button>` : ''}
            ${canCancel ? `<button class="danger-btn" data-job-action="cancel" data-job-id="${escapeHtml(job.id)}">Cancelar</button>` : ''}
            ${canRetry ? `<button class="soft-btn" data-job-action="retry" data-job-id="${escapeHtml(job.id)}">Reintentar</button>` : ''}
            <button class="danger-btn" data-delete-job="${escapeHtml(job.id)}">Eliminar</button>
          </div>
        </article>`;
      }).join('') : '<div class="empty-note">Todavía no hay trabajos autónomos en este proyecto.</div>'}</div>`;
    $('#createJobBtn', els.sheetBody)?.addEventListener('click', async () => {
      const title = $('#jobTitleInput', els.sheetBody).value.trim() || 'Trabajo autónomo';
      const promptText = $('#jobPromptInput', els.sheetBody).value.trim();
      if (!promptText) return;
      await apiFetch('/api/jobs', { method:'POST', body:JSON.stringify({ session_id:backendConversationId(), title, prompt:promptText }) });
      toast('Trabajo enviado al núcleo');
      renderJobs();
    });
    $$('[data-job-action]', els.sheetBody).forEach(btn => btn.addEventListener('click', async () => {
      const action = btn.dataset.jobAction;
      const id = btn.dataset.jobId;
      await apiFetch(`/api/jobs/${encodeURIComponent(id)}/${encodeURIComponent(action)}?session_id=${encodeURIComponent(backendConversationId())}`, { method:'POST' });
      toast(`Acción ${action} registrada`);
      setTimeout(renderJobs, 350);
    }));
    $$('[data-delete-job]', els.sheetBody).forEach(btn => btn.addEventListener('click', async () => {
      await apiFetch(`/api/jobs/${encodeURIComponent(btn.dataset.deleteJob)}?session_id=${encodeURIComponent(backendConversationId())}`, { method:'DELETE' });
      renderJobs();
    }));
  }

  async function renderKnowledgeSearch() {
    els.sheetBody.innerHTML = `
      <div class="form-row"><input class="text-input" id="knowledgeQuery" placeholder="Busca en memorias, documentos y conversaciones..."/><button class="primary-btn" id="knowledgeSearchBtn">Buscar</button></div>
      <div style="height:14px"></div><div id="knowledgeResults" class="empty-note">Escribe una consulta para buscar en el conocimiento del proyecto.</div>`;
    const execute = async () => {
      const query = $('#knowledgeQuery', els.sheetBody).value.trim();
      if (!query) return;
      const [remote, localHits] = await Promise.all([
        apiFetch(`/api/knowledge/search?session_id=${encodeURIComponent(backendConversationId())}&query=${encodeURIComponent(query)}&limit=8`),
        Promise.resolve(searchLocalChats(query))
      ]);
      const memories = remote.memories || [];
      const documents = remote.documents || [];
      $('#knowledgeResults', els.sheetBody).innerHTML = `
        ${searchSection('Conversaciones locales', localHits.map(hit => ({ title:hit.title, text:hit.preview })))}
        ${searchSection('Memoria', memories.map(item => ({ title:item.category || 'Recuerdo', text:item.content })))}
        ${searchSection('Documentos', documents.map(item => ({ title:item.file_name || 'Documento', text:item.excerpt || '' })))}
        ${!localHits.length && !memories.length && !documents.length ? '<div class="empty-note">No se encontraron coincidencias.</div>' : ''}`;
    };
    $('#knowledgeSearchBtn', els.sheetBody)?.addEventListener('click', execute);
    $('#knowledgeQuery', els.sheetBody)?.addEventListener('keydown', event => { if (event.key === 'Enter') execute(); });
  }

  function searchSection(title, items) {
    if (!items.length) return '';
    return `<section class="search-result-section"><h3>${escapeHtml(title)}</h3>${items.map(item => `<div class="search-hit"><div class="search-hit-title">${escapeHtml(item.title)}</div><div class="search-hit-text">${escapeHtml(String(item.text || '').slice(0,700))}</div></div>`).join('')}</section>`;
  }

  function searchLocalChats(query) {
    const needle = query.toLowerCase();
    return Object.values(state.chats)
      .filter(chat => chat.projectId === state.activeProjectId)
      .map(chat => {
        const text = (chat.messages || []).map(item => item.content || '').join('\n');
        const index = text.toLowerCase().indexOf(needle);
        if (index < 0 && !(chat.title || '').toLowerCase().includes(needle)) return null;
        const start = Math.max(0, index - 90);
        return { id:chat.id, title:chat.title || 'Conversación', preview:text.slice(start,start+260) };
      })
      .filter(Boolean)
      .slice(0,10);
  }

  async function renderExport() {
    const chat = currentChat();
    const count = chat?.messages?.length || 0;
    els.sheetBody.innerHTML = `
      <div class="project-hero"><h3>${escapeHtml(chat?.title || 'Conversación')}</h3><p>${count} mensajes · proyecto ${escapeHtml(currentProject()?.name || 'General')}</p></div>
      <div class="export-actions">
        <button class="export-card" id="exportMarkdown"><strong>Exportar Markdown</strong><span>Documento legible con toda la conversación.</span></button>
        <button class="export-card" id="exportJson"><strong>Exportar JSON</strong><span>Datos estructurados para respaldo o integración.</span></button>
      </div>`;
    $('#exportMarkdown', els.sheetBody)?.addEventListener('click', () => exportCurrentChat('markdown'));
    $('#exportJson', els.sheetBody)?.addEventListener('click', () => exportCurrentChat('json'));
  }

  function exportCurrentChat(format) {
    const chat = currentChat();
    if (!chat) return;
    const project = currentProject();
    const safeName = `${project?.name || 'JARVIS'}-${chat.title || 'conversacion'}`.replace(/[^a-z0-9_-]+/gi,'-').replace(/-+/g,'-').slice(0,80);
    if (format === 'json') {
      downloadFile(`${safeName}.json`, JSON.stringify({ project, chat, exportedAt:new Date().toISOString() }, null, 2), 'application/json');
      return;
    }
    const lines = [`# ${chat.title || 'Conversación JARVIS'}`, '', `Proyecto: ${project?.name || 'General'}`, `Exportado: ${new Date().toLocaleString()}`, ''];
    (chat.messages || []).forEach(message => {
      lines.push(message.role === 'user' ? '## Usuario' : '## J.A.R.V.I.S.', '', message.content || '', '');
    });
    downloadFile(`${safeName}.md`, lines.join('\n'), 'text/markdown');
  }

  function downloadFile(name, content, type) {
    const blob = new Blob([content], { type:`${type};charset=utf-8` });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    toast('Archivo exportado');
  }

  async function renderLibrary() {
    const data = await apiFetch(`/api/library?session_id=${encodeURIComponent(backendConversationId())}`);
    const docs = data.documents || [];
    const totalCharacters = docs.reduce((sum, doc) => sum + Number(doc.characters || 0), 0);
    els.sheetBody.innerHTML = `
      <div class="library-hero">
        <div class="library-hero-icon">▤</div>
        <div class="library-hero-copy"><h3>Biblioteca del proyecto</h3><p>Centraliza documentos, código y archivos de referencia para consultarlos desde JARVIS.</p></div>
        <button class="primary-btn" id="uploadFromPanel">Subir archivo</button>
      </div>
      <div class="library-stats">
        <span><strong>${docs.length}</strong> archivos</span>
        <span><strong>${totalCharacters.toLocaleString()}</strong> caracteres indexados</span>
        <span>PDF · Office · texto · código</span>
      </div>
      <div class="document-grid" id="libraryList">${docs.length ? docs.map(doc => listDocument(doc)).join('') : `
        <div class="library-empty">
          <span class="library-empty-icon">⇧</span>
          <strong>Tu biblioteca está vacía</strong>
          <small>Sube un archivo para resumirlo, buscar información o utilizarlo como contexto.</small>
        </div>`}</div>`;
    $('#uploadFromPanel', els.sheetBody)?.addEventListener('click', () => els.fileInput.click());
    $$('[data-delete-doc]', els.sheetBody).forEach(btn => btn.addEventListener('click', async () => {
      await apiFetch(`/api/library/${encodeURIComponent(btn.dataset.deleteDoc)}?session_id=${encodeURIComponent(backendConversationId())}`, { method: 'DELETE' });
      renderLibrary();
    }));
  }

  function listDocument(doc) {
    const extension = fileExtension(doc.file_name || doc.file_type || '');
    const icon = documentIcon(extension);
    return `<article class="document-card">
      <div class="document-icon ${escapeHtml(extension || 'file')}">${icon}</div>
      <div class="document-copy">
        <div class="document-title" title="${escapeHtml(doc.file_name)}">${escapeHtml(doc.file_name)}</div>
        <div class="document-meta">${escapeHtml((doc.file_type || extension || 'archivo').toUpperCase())} · ${Number(doc.characters || 0).toLocaleString()} caracteres</div>
        <div class="document-status"><span></span> Indexado y disponible</div>
      </div>
      <button class="document-delete" data-delete-doc="${escapeHtml(doc.id)}" aria-label="Eliminar documento" title="Eliminar">×</button>
    </article>`;
  }

  function fileExtension(name) {
    const clean = String(name || '').toLowerCase().split('?')[0];
    return clean.includes('.') ? clean.split('.').pop().slice(0, 6) : clean.replace(/[^a-z0-9]/g, '').slice(0, 6);
  }

  function documentIcon(extension) {
    if (extension === 'pdf') return 'PDF';
    if (['doc', 'docx'].includes(extension)) return 'W';
    if (['xls', 'xlsx', 'xlsm', 'csv'].includes(extension)) return 'X';
    if (['ppt', 'pptx'].includes(extension)) return 'P';
    if (['js', 'py', 'html', 'css', 'json'].includes(extension)) return '&lt;/&gt;';
    return '▤';
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

  async function renderProviders() {
    const data = await apiFetch('/api/providers');
    const gateway = data.gateway || {};
    const providers = gateway.providers || {};
    const configured = new Set(gateway.configured || []);
    const labels = { groq:'Groq', openai:'OpenAI', gemini:'Google Gemini', compatible:'Proveedor compatible', ollama:'Ollama' };
    const descriptions = {
      groq:'Velocidad, clasificación, conversación y respuestas cotidianas.',
      openai:'Razonamiento, programación, agentes y tareas complejas.',
      gemini:'Investigación, contexto amplio y procesamiento multimodal.',
      compatible:'Servidor adicional con interfaz compatible con OpenAI.',
      ollama:'Ruta local o privada para contingencia y trabajo sin proveedor externo.'
    };
    const order = gateway.order || Object.keys(providers);
    const cards = order.map(name => {
      const item = providers[name] || {};
      const stats = item.stats || {};
      const models = item.models || [];
      const isConfigured = configured.has(name) || Boolean(item.configured);
      return `<article class="provider-card ${isConfigured ? 'is-online' : 'is-optional'}">
        <div class="provider-card-head">
          <div class="provider-logo provider-${escapeHtml(name)}">${escapeHtml((labels[name] || name).slice(0,1))}</div>
          <div class="provider-state ${isConfigured ? 'online' : 'optional'}"><span></span>${isConfigured ? 'Configurado' : 'Opcional'}</div>
        </div>
        <h3>${escapeHtml(labels[name] || name)}</h3>
        <p>${escapeHtml(descriptions[name] || '')}</p>
        <div class="provider-models">${models.length ? models.map(model => `<span>${escapeHtml(model)}</span>`).join('') : '<span>Sin modelos configurados</span>'}</div>
        <div class="provider-metrics">
          <span><strong>${Math.round(Number(stats.success_rate || 0) * 100)}%</strong> éxito</span>
          <span><strong>${Number(stats.average_latency_ms || 0).toFixed(0)}</strong> ms</span>
          <span><strong>${Number(stats.requests || 0)}</strong> solicitudes</span>
        </div>
      </article>`;
    }).join('');
    els.sheetBody.innerHTML = `
      <div class="providers-hero">
        <div class="providers-icon">◫</div>
        <div><h3>Multi-Provider Gateway</h3><p>JARVIS selecciona automáticamente la ruta más conveniente según tarea, velocidad, capacidad y disponibilidad.</p></div>
      </div>
      <div class="provider-summary">
        <div><strong>${configured.size}</strong><span>proveedores configurados</span></div>
        <div><strong>${order.length}</strong><span>rutas reconocidas</span></div>
        <div><strong>${escapeHtml((gateway.order || []).join(' → ') || 'Sin orden')}</strong><span>orden base</span></div>
      </div>
      <div class="provider-grid">${cards}</div>
      <div style="height:18px"></div>
      <div class="route-lab">
        <div class="section-panel-title">Laboratorio de enrutamiento</div>
        <p>Escribe una tarea para ver qué proveedor priorizaría JARVIS. Esta vista no consume tokens.</p>
        <div class="form-row"><input class="text-input" id="routePreviewInput" placeholder="Ejemplo: investiga la inflación y compara fuentes oficiales"/><button class="primary-btn" id="routePreviewBtn">Analizar ruta</button></div>
        <div id="routePreviewResult" class="route-preview-result"></div>
      </div>`;
    $('#routePreviewBtn', els.sheetBody)?.addEventListener('click', async () => {
      const input = $('#routePreviewInput', els.sheetBody);
      const resultBox = $('#routePreviewResult', els.sheetBody);
      const message = input?.value.trim();
      if (!message) return;
      resultBox.innerHTML = '<div class="empty-note">Evaluando proveedores...</div>';
      try {
        const preview = await apiFetch('/api/providers/route-preview', { method:'POST', body:JSON.stringify({ message, mode:'auto' }) });
        const rows = preview.routes || [];
        resultBox.innerHTML = `<div class="route-preview-meta">Intención: <strong>${escapeHtml(preview.intent || 'general')}</strong> · modo: <strong>${escapeHtml(preview.mode || 'auto')}</strong></div>${rows.map((row,index) => `<div class="route-preview-row ${row.configured ? '' : 'disabled'}"><span class="route-rank">${index + 1}</span><div><strong>${escapeHtml(labels[row.provider] || row.provider)}</strong><small>${row.configured ? `${(row.models || []).length} modelo(s) elegible(s)` : 'No configurado'}</small></div><b>${row.score >= 0 ? Number(row.score).toFixed(2) : '—'}</b></div>`).join('')}`;
      } catch (error) {
        resultBox.innerHTML = `<div class="empty-note">${escapeHtml(error.message || 'No se pudo evaluar la ruta.')}</div>`;
      }
    });
  }


  async function renderResilience() {
    const data = await apiFetch(`/api/resilience/status?session_id=${encodeURIComponent(backendConversationId())}`);
    const providers = data.providers || {};
    const summary = data.summary_24h || {};
    const limits = data.limits || {};
    const recent = data.recent_runs || [];
    const providerCards = [
      ['Groq', Boolean(providers.groq?.configured), (providers.groq?.models || []).map(item => item.model).join(', ') || 'Sin modelos'],
      ['OpenAI', Boolean(providers.openai?.configured), (providers.openai?.models || []).join(', ') || 'Opcional'],
      ['Google Gemini', Boolean(providers.gemini?.configured), (providers.gemini?.models || []).join(', ') || 'Opcional'],
      ['Proveedor compatible', Boolean(providers.openai_compatible?.configured), (providers.openai_compatible?.models || []).join(', ') || 'Opcional'],
      ['Ollama local', Boolean(providers.ollama?.configured), (providers.ollama?.models || []).join(', ') || 'Opcional'],
      ['Rutas locales', true, 'Cálculo, SymPy, documentos, memoria, caché y búsqueda'],
    ];
    els.sheetBody.innerHTML = `
      <div class="resilience-hero">
        <div class="resilience-icon">⟲</div>
        <div><h3>Núcleo de resolución resistente</h3><p>JARVIS prueba rutas locales, caché, modelos, proveedores secundarios y búsqueda antes de entregar un resultado degradado.</p></div>
      </div>
      <div class="panel-grid resilience-grid">
        ${providerCards.map(([name,configured,detail]) => `<div class="panel-card resilience-provider"><div class="provider-state ${configured ? 'online' : 'optional'}"><span></span>${configured ? 'Activo' : 'Opcional'}</div><h3>${escapeHtml(name)}</h3><p>${escapeHtml(detail)}</p></div>`).join('')}
      </div>
      <div style="height:14px"></div>
      <div class="panel-grid">
        <div class="panel-card"><h3>Resoluciones en 24 h</h3><p>${Number(summary.total || 0).toLocaleString()} solicitudes registradas</p></div>
        <div class="panel-card"><h3>Verificadas</h3><p>${Number(summary.verified || 0).toLocaleString()} resultados superaron la comprobación</p></div>
        <div class="panel-card"><h3>Intentos promedio</h3><p>${Number(summary.average_attempts || 0).toFixed(1)} rutas por solicitud</p></div>
        <div class="panel-card"><h3>Presupuesto de resolución</h3><p>Hasta ${limits.max_resolution_attempts || 0} rutas · ${limits.web_search_attempts || 0} intentos de búsqueda</p></div>
      </div>
      <div style="height:16px"></div>
      <div class="section-panel-title">Ejecuciones recientes</div>
      <div class="list-stack">${recent.length ? recent.map(run => `
        <div class="list-item resolution-run">
          <div class="list-main">
            <div class="list-title">${escapeHtml(humanIntent(run.intent || 'general'))}</div>
            <div class="list-sub">${escapeHtml(humanRoute(run.route || 'resilient'))} · ${Number(run.attempts || 0)} intento(s) · ${run.verified ? 'verificado' : 'resultado parcial'}</div>
          </div>
          <span class="run-status ${run.verified ? 'verified' : 'partial'}">${run.verified ? '✓' : '•'}</span>
        </div>`).join('') : '<div class="empty-note">Todavía no hay ejecuciones registradas.</div>'}</div>`;
  }

  async function renderPerformance() {
    const data = await apiFetch(`/api/performance?session_id=${encodeURIComponent(backendConversationId())}&hours=24`);
    const runtime = data.runtime || {};
    const memory = runtime.cache?.memory || {};
    const redis = runtime.cache?.redis || {};
    const metrics = runtime.metrics?.operations || {};
    const circuits = runtime.circuits || {};
    const circuitEntries = Object.entries(circuits);
    const openCircuits = circuitEntries.filter(([,value]) => value.state === 'open');
    const chatMetric = metrics['chat:resolve'] || {};
    const jobs = data.jobs || {};
    els.sheetBody.innerHTML = `
      <div class="performance-hero">
        <div class="performance-icon">⌁</div>
        <div><h3>Multi-Provider Performance Core</h3><p>Telemetría local para detectar lentitud, reutilizar resultados y aislar proveedores que fallen repetidamente.</p></div>
      </div>
      <div class="panel-grid performance-grid">
        <div class="panel-card metric-card"><span>Latencia media</span><strong>${Number(chatMetric.avg_ms || 0).toFixed(0)} ms</strong><small>P95 ${Number(chatMetric.p95_ms || 0).toFixed(0)} ms</small></div>
        <div class="panel-card metric-card"><span>Caché L1</span><strong>${Math.round(Number(memory.hit_rate || 0) * 100)}%</strong><small>${Number(memory.items || 0)} objetos activos</small></div>
        <div class="panel-card metric-card"><span>Solicitudes unificadas</span><strong>${Number(runtime.singleflight?.collapsed_requests || 0)}</strong><small>trabajos duplicados evitados</small></div>
        <div class="panel-card metric-card"><span>Circuitos abiertos</span><strong>${openCircuits.length}</strong><small>${circuitEntries.length} rutas observadas</small></div>
        <div class="panel-card metric-card"><span>Workers</span><strong>${Number(jobs.workers || 0)}</strong><small>${Number(jobs.active_futures || 0)} activos</small></div>
        <div class="panel-card metric-card"><span>Redis</span><strong>${redis.configured ? (redis.connected ? 'Activo' : 'Respaldo') : 'Opcional'}</strong><small>${Number(redis.hits || 0)} aciertos</small></div>
      </div>
      <div style="height:16px"></div>
      <div class="section-panel-title">Operaciones observadas</div>
      <div class="performance-table">${Object.entries(metrics).length ? Object.entries(metrics).sort((a,b) => Number(b[1].requests || 0) - Number(a[1].requests || 0)).slice(0,14).map(([name,item]) => `<div class="performance-row"><span>${escapeHtml(name)}</span><strong>${Number(item.avg_ms || 0).toFixed(0)} ms</strong><small>${Math.round(Number(item.success_rate || 0)*100)}% éxito · ${Number(item.requests || 0)} solicitudes</small></div>`).join('') : '<div class="empty-note">La telemetría aparecerá después de utilizar JARVIS.</div>'}</div>
      <div style="height:16px"></div>
      <div class="section-panel-title">Circuitos de protección</div>
      <div class="list-stack">${circuitEntries.length ? circuitEntries.map(([name,item]) => `<div class="list-item"><div class="list-main"><div class="list-title">${escapeHtml(name)}</div><div class="list-sub">${escapeHtml(item.state || 'closed')} · ${Number(item.failures || 0)} fallos · ${Number(item.successes || 0)} éxitos</div></div><span class="run-status ${item.state === 'open' ? 'partial' : 'verified'}">${item.state === 'open' ? '!' : '✓'}</span></div>`).join('') : '<div class="empty-note">No hay circuitos registrados todavía.</div>'}</div>`;
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
    const response = await resilientFetch(apiUrl(path), {
      headers: { 'Content-Type':'application/json', ...(options.headers || {}) },
      ...options
    }, { attempts: options.method && options.method !== 'GET' ? 2 : 3, retryStatuses: [429, 502, 503, 504] });
    const raw = await response.text();
    let data = {};
    try { data = raw ? JSON.parse(raw) : {}; }
    catch { throw new Error(`Respuesta no válida del servidor (HTTP ${response.status}).`); }
    if (!response.ok) throw new Error(data.detail || data.reply || `Error HTTP ${response.status}`);
    return data;
  }

  async function requestJarvis(payload, signal) {
    const requestOptions = {
      method: 'POST',
      headers: { 'Content-Type':'application/json', 'Accept':'application/x-ndjson, application/json' },
      body: JSON.stringify(payload),
      signal
    };

    const parseStandardResponse = async response => {
      const raw = await response.text();
      let data = {};
      try { data = raw ? JSON.parse(raw) : {}; }
      catch { throw new Error(`El servidor respondió con contenido no válido (HTTP ${response.status}).`); }
      if (!response.ok) {
        const retry = data.retry_after_seconds ? ` Intenta nuevamente en ${data.retry_after_seconds} segundos.` : '';
        throw new Error((data.detail || data.reply || `Error HTTP ${response.status}`) + retry);
      }
      return data;
    };

    try {
      const response = await resilientFetch(apiUrl('/api/jarvis/stream'), requestOptions, { attempts: 3, retryStatuses: [429, 502, 503, 504] });
      const contentType = response.headers.get('content-type') || '';
      if (!response.ok || !response.body || !contentType.includes('application/x-ndjson')) {
        return parseStandardResponse(response);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let finalData = null;
      while (true) {
        const { value, done } = await reader.read();
        buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          if (!line.trim()) continue;
          let event;
          try { event = JSON.parse(line); }
          catch { continue; }
          if (event.type === 'progress') {
            const stage = event.stage || 'Trabajando';
            els.thinkingText.textContent = stage;
            setStatus(stage, 'warning');
          } else if (event.type === 'final') {
            finalData = event.data || {};
          }
        }
        if (done) break;
      }
      if (buffer.trim()) {
        try {
          const event = JSON.parse(buffer);
          if (event.type === 'final') finalData = event.data || {};
        } catch {}
      }
      if (!finalData) throw new Error('La conexión terminó antes de recibir el resultado final.');
      return finalData;
    } catch (error) {
      if (error.name === 'AbortError') throw error;
      setStatus('Recuperando resultado por ruta compatible', 'warning');
      const fallback = await resilientFetch(apiUrl('/api/jarvis'), requestOptions, { attempts: 3, retryStatuses: [429, 502, 503, 504] });
      return parseStandardResponse(fallback);
    }
  }

  function createRequestId() {
    if (window.crypto?.randomUUID) return window.crypto.randomUUID();
    return `req_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
  }

  async function resilientFetch(url, options = {}, config = {}) {
    const attempts = Math.max(1, Number(config.attempts || 3));
    const retryStatuses = new Set(config.retryStatuses || [429, 502, 503, 504]);
    let lastError = null;
    for (let index = 0; index < attempts; index++) {
      try {
        const response = await fetch(url, options);
        if (!retryStatuses.has(response.status) || index === attempts - 1) return response;
        const retryHeader = Number(response.headers.get('Retry-After') || 0);
        const waitMs = retryHeader > 0 ? retryHeader * 1000 : Math.min(900 * (2 ** index), 6000);
        setStatus(`Recuperando conexión · intento ${index + 2}`, 'warning');
        await sleep(waitMs);
      } catch (error) {
        if (error.name === 'AbortError') throw error;
        lastError = error;
        if (index === attempts - 1) throw error;
        setStatus(`Buscando ruta alternativa · intento ${index + 2}`, 'warning');
        await sleep(Math.min(900 * (2 ** index), 6000));
      }
    }
    throw lastError || new Error('No fue posible establecer conexión.');
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

  function updateOfflineBanner() {
    els.offlineBanner?.classList.toggle('show', !navigator.onLine);
  }

  async function registerServiceWorker() {
    if (!('serviceWorker' in navigator)) return;
    try {
      const swUrl = new URL('./service-worker.js', document.baseURI).href;
      await navigator.serviceWorker.register(swUrl);
    } catch (error) {
      console.warn('No se pudo registrar el modo offline:', error);
    }
  }

  function humanIntent(intent) {
    return ({ research:'Investigación', documents:'Documentos', math:'Matemática', code:'Programación', writing:'Escritura', planning:'Planificación', memory:'Memoria', reminders:'Recordatorios', general:'Conversación' })[intent] || intent;
  }

  function humanRoute(route) {
    return ({ direct:'Ruta local', direct_web:'Búsqueda directa', autonomous:'Agente autónomo', cache:'Caché', degraded:'Modo local', degraded_web:'Web en modo local', provider_research:'Investigación multirruta', secondary_provider:'Proveedor secundario', multi_provider:'Gateway multimodelo', similar_cache:'Caché similar', resilient_web:'Búsqueda resistente', resilient_local:'Resolución local', resilient_documents:'Biblioteca local', verified_repair:'Respuesta reparada' })[route] || route;
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
