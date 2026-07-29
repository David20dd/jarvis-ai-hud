(() => {
  'use strict';

  const $ = selector => document.querySelector(selector);
  const $$ = selector => [...document.querySelectorAll(selector)];
  const escapeHTML = value => String(value ?? '').replace(/[&<>'"]/g, char => ({
    '&':'&amp;', '<':'&lt;', '>':'&gt;', "'":'&#39;', '"':'&quot;'
  }[char]));

  const commands = [
    { id:'research', label:'Investigar', description:'Buscar, contrastar y citar fuentes', shortcut:'/investigar', icon:'search', mode:'research', prompt:'Investiga este tema, contrasta fuentes confiables y cita cada dato importante: ' },
    { id:'fast', label:'Respuesta rápida', description:'Usar la ruta de menor latencia', shortcut:'/rapido', icon:'sparkles', mode:'fast', prompt:'' },
    { id:'math', label:'Resolver matemática', description:'Cálculo exacto y explicación paso a paso', shortcut:'/matematica', icon:'target', mode:'math', prompt:'Resuelve con exactitud y explica solo los pasos necesarios: ' },
    { id:'professional', label:'Modo profesional', description:'Plan, especialistas y control de calidad', shortcut:'/profesional', icon:'cpu', mode:'professional', prompt:'Resuelve profesionalmente este objetivo, con plan, riesgos y próximos pasos: ' },
    { id:'mission', label:'Crear misión', description:'Trabajo por etapas con checkpoints', shortcut:'/mision', icon:'target', view:'missions' },
    { id:'canvas', label:'Abrir Canvas', description:'Crear o editar documentos y código', shortcut:'/canvas', icon:'canvas', workspace:true },
    { id:'knowledge', label:'Buscar memoria', description:'Revisar conocimiento y documentos', shortcut:'/memoria', icon:'knowledge', view:'knowledge' },
    { id:'voice', label:'Hablar con JARVIS', description:'Iniciar dictado por voz', shortcut:'/voz', icon:'volume', voice:true },
    { id:'telegram', label:'Abrir Telegram', description:'Estado, multimedia y configuración', shortcut:'/telegram', icon:'telegram', view:'channels' },
  ];

  const state = {
    commandIndex: 0,
    filteredCommands: commands,
    workspaceItems: [],
    workspaceFilter: '',
    workspaceOpen: false,
  };

  const elements = {};

  document.addEventListener('DOMContentLoaded', init);

  function init() {
    Object.assign(elements, {
      input:$('#messageInput'),
      composer:$('#composer'),
      fileInput:$('#fileInput'),
      slashMenu:$('#v100SlashMenu'),
      workspaceButton:$('#v100WorkspaceBtn'),
      workspaceDrawer:$('#v100WorkspaceDrawer'),
      workspaceClose:$('#v100WorkspaceClose'),
      workspaceList:$('#v100WorkspaceList'),
      newCanvas:$('#v100NewCanvas'),
      editor:$('#v100Editor'),
      editorId:$('#v100EditorId'),
      editorTitle:$('#v100EditorTitle'),
      editorKind:$('#v100EditorKind'),
      editorContent:$('#v100EditorContent'),
      editorCancel:$('#v100EditorCancel'),
      voiceButton:$('#voiceBtn'),
    });
    if (!window.JARVIS_APP || !elements.input || !elements.workspaceDrawer) return;
    bindCommands();
    bindWorkspace();
    bindDropZone();
    probeV100();
  }

  function icon(name) {
    return `<svg class="icon" aria-hidden="true"><use href="#i-${name}"></use></svg>`;
  }

  function bindCommands() {
    elements.input.addEventListener('input', updateSlashMenu);
    elements.input.addEventListener('keydown', event => {
      if (elements.slashMenu.hidden) return;
      if (event.key === 'ArrowDown') {
        event.preventDefault();
        state.commandIndex = Math.min(state.commandIndex + 1, state.filteredCommands.length - 1);
        renderSlashMenu();
      } else if (event.key === 'ArrowUp') {
        event.preventDefault();
        state.commandIndex = Math.max(state.commandIndex - 1, 0);
        renderSlashMenu();
      } else if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        executeCommand(state.filteredCommands[state.commandIndex]);
      } else if (event.key === 'Escape') {
        closeSlashMenu();
      }
    }, true);
    elements.slashMenu.addEventListener('click', event => {
      const button = event.target.closest('[data-v100-command]');
      if (!button) return;
      executeCommand(commands.find(item => item.id === button.dataset.v100Command));
    });
    document.addEventListener('click', event => {
      if (!event.target.closest('#composer,#v100SlashMenu')) closeSlashMenu();
    });
  }

  function updateSlashMenu() {
    const raw = elements.input.value;
    if (!raw.startsWith('/') || raw.includes('\n')) return closeSlashMenu();
    const query = raw.slice(1).trim().toLowerCase();
    state.filteredCommands = commands.filter(command =>
      !query
      || command.id.includes(query)
      || command.label.toLowerCase().includes(query)
      || command.description.toLowerCase().includes(query)
    );
    state.commandIndex = 0;
    if (!state.filteredCommands.length) return closeSlashMenu();
    renderSlashMenu();
  }

  function renderSlashMenu() {
    elements.slashMenu.innerHTML = state.filteredCommands.map((command, index) => `
      <button type="button" role="option" aria-selected="${index === state.commandIndex}" class="${index === state.commandIndex ? 'active' : ''}" data-v100-command="${escapeHTML(command.id)}">
        <span>${icon(command.icon)}</span>
        <span><strong>${escapeHTML(command.label)}</strong><small>${escapeHTML(command.description)}</small></span>
        <kbd>${escapeHTML(command.shortcut)}</kbd>
      </button>
    `).join('');
    elements.slashMenu.hidden = false;
    elements.slashMenu.querySelector('.active')?.scrollIntoView({ block:'nearest' });
  }

  function closeSlashMenu() {
    elements.slashMenu.hidden = true;
    elements.slashMenu.innerHTML = '';
  }

  function executeCommand(command) {
    if (!command) return;
    closeSlashMenu();
    elements.input.value = '';
    if (command.mode) window.JARVIS_APP.setMode(command.mode);
    if (command.prompt !== undefined) window.JARVIS_APP.setPrompt(command.prompt);
    if (command.view) window.JARVIS_APP.openView(command.view);
    if (command.workspace) openWorkspace();
    if (command.voice) elements.voiceButton?.click();
  }

  function bindDropZone() {
    const zone = elements.composer.closest('.composer-zone');
    if (!zone) return;
    ['dragenter','dragover'].forEach(name => zone.addEventListener(name, event => {
      event.preventDefault();
      zone.classList.add('drop-ready');
    }));
    ['dragleave','drop'].forEach(name => zone.addEventListener(name, event => {
      event.preventDefault();
      zone.classList.remove('drop-ready');
    }));
    zone.addEventListener('drop', event => {
      const files = [...(event.dataTransfer?.files || [])];
      if (!files.length) return;
      try {
        const transfer = new DataTransfer();
        files.forEach(file => transfer.items.add(file));
        elements.fileInput.files = transfer.files;
        elements.fileInput.dispatchEvent(new Event('change', { bubbles:true }));
      } catch {
        window.JARVIS_APP.toast('Usa el botón de adjuntar para seleccionar estos archivos.');
      }
    });
    document.addEventListener('paste', event => {
      const files = [...(event.clipboardData?.files || [])];
      if (!files.length || document.activeElement !== elements.input) return;
      try {
        const transfer = new DataTransfer();
        files.forEach(file => transfer.items.add(file));
        elements.fileInput.files = transfer.files;
        elements.fileInput.dispatchEvent(new Event('change', { bubbles:true }));
      } catch {}
    });
  }

  function bindWorkspace() {
    elements.workspaceButton?.addEventListener('click', () => state.workspaceOpen ? closeWorkspace() : openWorkspace());
    elements.workspaceClose?.addEventListener('click', closeWorkspace);
    elements.newCanvas?.addEventListener('click', () => openEditor());
    elements.editorCancel?.addEventListener('click', closeEditor);
    elements.editor?.addEventListener('submit', saveEditor);
    $$('[data-workspace-filter]').forEach(button => button.addEventListener('click', () => {
      state.workspaceFilter = button.dataset.workspaceFilter || '';
      $$('[data-workspace-filter]').forEach(item => item.classList.toggle('active', item === button));
      renderWorkspace();
    }));
    elements.workspaceList?.addEventListener('click', event => {
      const remove = event.target.closest('[data-workspace-delete]');
      if (remove) {
        event.stopPropagation();
        deleteWorkspaceItem(remove.dataset.workspaceDelete);
        return;
      }
      const card = event.target.closest('[data-workspace-item]');
      if (!card) return;
      const item = state.workspaceItems.find(entry => entry.id === card.dataset.workspaceItem);
      if (item) openEditor(item);
    });
    window.addEventListener('jarvis:save-canvas', async event => {
      const detail = event.detail || {};
      try {
        const response = await api('/api/v100/workspace', {
          method:'POST',
          body:JSON.stringify({
            session_id:window.JARVIS_APP.backendSessionId(),
            title:String(detail.title || 'Canvas JARVIS').slice(0,300),
            content:String(detail.content || ''),
            kind:detail.kind || 'document',
            project_name:window.JARVIS_APP.project || 'General',
            metadata:{ source:'conversation', created_by:'user_action' }
          })
        });
        window.JARVIS_APP.toast('Guardado en Canvas.');
        await openWorkspace();
        const item = response.item;
        if (item) openEditor(item);
      } catch (error) {
        window.JARVIS_APP.toast(error.message || 'No fue posible guardar en Canvas.');
      }
    });
    document.addEventListener('keydown', event => {
      const modifier = event.ctrlKey || event.metaKey;
      if (modifier && event.shiftKey && event.key.toLowerCase() === 'c') {
        event.preventDefault();
        state.workspaceOpen ? closeWorkspace() : openWorkspace();
      } else if (event.key === 'Escape' && state.workspaceOpen) {
        closeWorkspace();
      }
    });
  }

  async function openWorkspace() {
    state.workspaceOpen = true;
    document.body.classList.add('v100-workspace-open');
    elements.workspaceDrawer.setAttribute('aria-hidden', 'false');
    elements.workspaceButton?.classList.add('active');
    await loadWorkspace();
  }

  function closeWorkspace() {
    state.workspaceOpen = false;
    document.body.classList.remove('v100-workspace-open');
    elements.workspaceDrawer.setAttribute('aria-hidden', 'true');
    elements.workspaceButton?.classList.remove('active');
    closeEditor();
  }

  async function loadWorkspace() {
    elements.workspaceList.innerHTML = '<div class="v100-empty">Cargando tu espacio…</div>';
    try {
      const query = new URLSearchParams({
        session_id:window.JARVIS_APP.backendSessionId(),
        project_name:window.JARVIS_APP.project || 'General',
        limit:'100'
      });
      const data = await api(`/api/v100/workspace?${query}`);
      state.workspaceItems = data.items || [];
      renderWorkspace();
    } catch (error) {
      elements.workspaceList.innerHTML = `<div class="v100-empty">No fue posible cargar el Canvas.<br><small>${escapeHTML(error.message || 'Conexión no disponible')}</small><br><br><button class="soft-btn" id="v100WorkspaceRetry" type="button">Reintentar</button></div>`;
      $('#v100WorkspaceRetry')?.addEventListener('click', loadWorkspace);
    }
  }

  function renderWorkspace() {
    const items = state.workspaceItems.filter(item => !state.workspaceFilter || item.kind === state.workspaceFilter);
    if (!items.length) {
      elements.workspaceList.innerHTML = '<div class="v100-empty">Tu Canvas está vacío.<br>Guarda una respuesta o crea un documento nuevo.</div>';
      return;
    }
    elements.workspaceList.innerHTML = items.map(item => `
      <article class="v100-workspace-card" tabindex="0" data-workspace-item="${escapeHTML(item.id)}">
        <span>${icon(item.kind === 'code' ? 'cpu' : 'canvas')}</span>
        <div><strong>${escapeHTML(item.title)}</strong><small>${escapeHTML(kindLabel(item.kind))} · v${Number(item.version || 1)} · ${escapeHTML(relativeTime(item.updated_at))}</small></div>
        <button type="button" data-workspace-delete="${escapeHTML(item.id)}" aria-label="Eliminar ${escapeHTML(item.title)}" title="Eliminar">${icon('trash')}</button>
      </article>
    `).join('');
  }

  function kindLabel(kind) {
    return ({document:'Documento',note:'Nota',code:'Código',table:'Tabla',checklist:'Lista',canvas:'Canvas'})[kind] || 'Elemento';
  }

  function relativeTime(timestamp) {
    const milliseconds = Number(timestamp || 0) * (Number(timestamp || 0) < 10_000_000_000 ? 1000 : 1);
    const difference = Date.now() - milliseconds;
    if (difference < 60_000) return 'ahora';
    if (difference < 3_600_000) return `${Math.floor(difference / 60_000)} min`;
    if (difference < 86_400_000) return `${Math.floor(difference / 3_600_000)} h`;
    return new Date(milliseconds).toLocaleDateString('es-HN', { day:'numeric', month:'short' });
  }

  function openEditor(item = null) {
    elements.workspaceList.hidden = true;
    elements.editor.hidden = false;
    elements.editorId.value = item?.id || '';
    elements.editorTitle.value = item?.title || '';
    elements.editorKind.value = item?.kind || 'document';
    elements.editorContent.value = item?.content || '';
    setTimeout(() => (item ? elements.editorContent : elements.editorTitle).focus(), 30);
  }

  function closeEditor() {
    if (!elements.editor) return;
    elements.editor.hidden = true;
    elements.workspaceList.hidden = false;
    elements.editor.reset();
    elements.editorId.value = '';
  }

  async function saveEditor(event) {
    event.preventDefault();
    const itemId = elements.editorId.value;
    const payload = {
      session_id:window.JARVIS_APP.backendSessionId(),
      title:elements.editorTitle.value.trim(),
      content:elements.editorContent.value,
      kind:elements.editorKind.value,
      project_name:window.JARVIS_APP.project || 'General',
      metadata:{ source:'canvas_editor' }
    };
    const submit = elements.editor.querySelector('[type="submit"]');
    submit.disabled = true;
    submit.textContent = 'Guardando…';
    try {
      await api(itemId ? `/api/v100/workspace/${encodeURIComponent(itemId)}` : '/api/v100/workspace', {
        method:itemId ? 'PUT' : 'POST',
        body:JSON.stringify(payload)
      });
      closeEditor();
      await loadWorkspace();
      window.JARVIS_APP.toast('Canvas guardado.');
    } catch (error) {
      window.JARVIS_APP.toast(error.message || 'No fue posible guardar.');
    } finally {
      submit.disabled = false;
      submit.textContent = 'Guardar';
    }
  }

  async function deleteWorkspaceItem(itemId) {
    if (!confirm('¿Eliminar este elemento del Canvas?')) return;
    try {
      const query = new URLSearchParams({ session_id:window.JARVIS_APP.backendSessionId() });
      await api(`/api/v100/workspace/${encodeURIComponent(itemId)}?${query}`, { method:'DELETE' });
      state.workspaceItems = state.workspaceItems.filter(item => item.id !== itemId);
      renderWorkspace();
      window.JARVIS_APP.toast('Elemento eliminado.');
    } catch (error) {
      window.JARVIS_APP.toast(error.message || 'No fue posible eliminarlo.');
    }
  }

  async function probeV100() {
    try {
      const query = new URLSearchParams({ session_id:window.JARVIS_APP.backendSessionId() });
      const data = await api(`/api/v100/status?${query}`, {}, 18000);
      document.body.dataset.jarvisVersion = data.version || '100.0.0';
      document.body.classList.toggle('v100-degraded', data.status !== 'ok');
    } catch {
      document.body.classList.add('v100-degraded');
    }
  }

  function api(path, options = {}, timeoutMs = 25000) {
    return window.JARVIS_APP.request(path, options, { attempts:1, timeoutMs });
  }
})();

