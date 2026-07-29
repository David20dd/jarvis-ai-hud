(() => {
  'use strict';

  const VERSION = '101.0.0';
  const state = {
    busy: false,
    reporting: false,
    reported: new Set(),
    observer: null
  };

  const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, character => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;'
  }[character]));

  const clamp = (value, min, max) => Math.min(max, Math.max(min, Number(value) || 0));

  function app() {
    return window.JARVIS_APP || null;
  }

  function currentSession() {
    try {
      return app()?.backendSessionId?.() || 'browser-v101';
    } catch {
      return 'browser-v101';
    }
  }

  async function request(path, options = {}) {
    const client = app();
    if (!client?.request) throw new Error('El núcleo de JARVIS todavía no está disponible.');
    return client.request(path, options, { attempts: 2, timeoutMs: 30000 });
  }

  function sanitizeError(value) {
    const message = String(value?.message || value || 'Error desconocido')
      .replace(/(?:sk|gsk|AIza|xoxb|ghp)[-_A-Za-z0-9]{12,}/g, '[credencial protegida]')
      .replace(/https?:\/\/\S+/g, '[url]')
      .slice(0, 420);
    return message || 'Error desconocido';
  }

  async function reportBrowserIssue(error, context = 'browser') {
    if (state.reporting) return;
    const message = sanitizeError(error);
    const fingerprint = `${context}:${message}`;
    if (state.reported.has(fingerprint) || state.reported.size >= 12) return;
    state.reported.add(fingerprint);
    state.reporting = true;
    try {
      await request('/api/v101/issues/report', {
        method: 'POST',
        body: JSON.stringify({
          source: 'frontend',
          category: context,
          severity: 'medium',
          title: `Incidencia del navegador: ${context}`,
          detail: message,
          context: {
            version: VERSION,
            path: location.pathname,
            viewport: `${window.innerWidth}x${window.innerHeight}`,
            online: navigator.onLine
          }
        })
      });
    } catch {
      // Un fallo del reportero nunca debe afectar la aplicación.
    } finally {
      state.reporting = false;
    }
  }

  window.addEventListener('error', event => {
    const target = event.target;
    if (target && target !== window && target.tagName) {
      reportBrowserIssue(`No se cargó el recurso ${target.tagName.toLowerCase()}`, 'resource');
      return;
    }
    reportBrowserIssue(event.error || event.message, 'javascript');
  }, true);

  window.addEventListener('unhandledrejection', event => {
    reportBrowserIssue(event.reason, 'promise');
  });

  function issueCard(issue) {
    const severity = escapeHTML(issue.severity || 'medium');
    return `
      <article class="v101-item">
        <div class="v101-item-head">
          <strong title="${escapeHTML(issue.title)}">${escapeHTML(issue.title || 'Incidencia')}</strong>
          <span class="v101-badge ${severity}">${severity}</span>
        </div>
        <small>${Number(issue.occurrences || 1)} ocurrencia(s) · ${escapeHTML(issue.source || 'sistema')}</small>
        <div class="v101-actions">
          <button class="v101-action" data-v101-issue="${escapeHTML(issue.id)}" data-status="monitoring">Monitorear</button>
          <button class="v101-action" data-v101-issue="${escapeHTML(issue.id)}" data-status="resolved">Resolver</button>
        </div>
      </article>`;
  }

  function proposalCard(proposal) {
    const status = escapeHTML(proposal.status || 'proposed');
    return `
      <article class="v101-item">
        <div class="v101-item-head">
          <strong title="${escapeHTML(proposal.title)}">${escapeHTML(proposal.title || 'Propuesta')}</strong>
          <span class="v101-badge">${status}</span>
        </div>
        <small>Riesgo ${escapeHTML(proposal.risk_level || 'low')} · requiere aprobación humana</small>
        ${status === 'proposed' ? `
          <div class="v101-actions">
            <button class="v101-action" data-v101-proposal="${escapeHTML(proposal.id)}" data-decision="approved">Aprobar plan</button>
            <button class="v101-action" data-v101-proposal="${escapeHTML(proposal.id)}" data-decision="rejected">Descartar</button>
          </div>` : ''}
      </article>`;
  }

  function reliabilityHTML(status, issues, proposals) {
    const reliability = status?.reliability || status || {};
    const issueCounts = reliability.issues || {};
    const proposalCounts = reliability.proposals || {};
    const openIssues = issues.filter(item => !['resolved', 'dismissed'].includes(item.status));
    const activeProposals = proposals.filter(item => item.status === 'proposed');
    const rawQuality = reliability?.latest_quality?.score;
    const quality = clamp(rawQuality == null ? (openIssues.length ? 82 : 100) : Number(rawQuality) * 100, 0, 100);
    return `
      <section class="v101-reliability" data-v101-root>
        <header class="v101-reliability-head">
          <div>
            <span class="v101-kicker">RELIABILITY & SELF-IMPROVEMENT · v101</span>
            <h3>Calidad verificable, mejoras bajo tu control</h3>
            <p>JARVIS detecta fallos, agrupa incidencias y propone correcciones. Nunca modifica código ni despliega sin autorización.</p>
          </div>
          <button class="soft-btn" type="button" data-v101-diagnostics>Ejecutar diagnóstico</button>
        </header>
        <div class="v101-metrics">
          <article class="v101-metric">
            <strong>${quality}%</strong><span>Puntuación de calidad</span>
            <div class="v101-quality-bar" aria-label="Calidad ${quality}%"><i style="width:${quality}%"></i></div>
          </article>
          <article class="v101-metric"><strong>${Number((issueCounts.open || 0) + (issueCounts.monitoring || 0) || openIssues.length)}</strong><span>Incidencias abiertas</span></article>
          <article class="v101-metric"><strong>${Number(proposalCounts.proposed ?? activeProposals.length)}</strong><span>Propuestas pendientes</span></article>
        </div>
        <div class="v101-columns">
          <section class="v101-section">
            <h4>Incidencias recientes</h4>
            <div class="v101-list">${openIssues.length ? openIssues.slice(0, 4).map(issueCard).join('') : '<div class="v101-empty">No hay errores activos registrados.</div>'}</div>
          </section>
          <section class="v101-section">
            <h4>Mejoras propuestas</h4>
            <div class="v101-list">${activeProposals.length ? activeProposals.slice(0, 4).map(proposalCard).join('') : '<div class="v101-empty">Ejecuta un diagnóstico para buscar oportunidades de mejora.</div>'}</div>
          </section>
        </div>
      </section>`;
  }

  async function loadReliability(force = false) {
    const panel = document.querySelector('#panelContent');
    if (!panel || !panel.querySelector('.nexus-hero')) return;
    if (state.busy || (!force && panel.querySelector('[data-v101-root]'))) return;
    state.busy = true;
    try {
      const session = encodeURIComponent(currentSession());
      const [status, issueData, proposalData] = await Promise.all([
        request(`/api/v101/status?session_id=${session}`),
        request(`/api/v101/issues?session_id=${session}&limit=12`),
        request(`/api/v101/improvements/proposals?session_id=${session}&limit=12`)
      ]);
      panel.querySelector('[data-v101-root]')?.remove();
      const hero = panel.querySelector('.nexus-hero');
      hero.insertAdjacentHTML('afterend', reliabilityHTML(
        status,
        issueData.issues || [],
        proposalData.proposals || []
      ));
      bindReliabilityActions(panel);
      document.body.classList.add('v101-ready');
    } catch (error) {
      if (force) app()?.toast?.(sanitizeError(error));
    } finally {
      state.busy = false;
    }
  }

  function setLoading(root, value) {
    root?.classList.toggle('v101-loading', Boolean(value));
  }

  function bindReliabilityActions(panel) {
    const root = panel.querySelector('[data-v101-root]');
    if (!root || root.dataset.bound === 'true') return;
    root.dataset.bound = 'true';
    root.addEventListener('click', async event => {
      const diagnostics = event.target.closest('[data-v101-diagnostics]');
      const issueButton = event.target.closest('[data-v101-issue]');
      const proposalButton = event.target.closest('[data-v101-proposal]');
      if (!diagnostics && !issueButton && !proposalButton) return;
      setLoading(root, true);
      try {
        if (diagnostics) {
          const result = await request('/api/v101/diagnostics/run', {
            method: 'POST',
            body: JSON.stringify({ session_id: currentSession(), include_deep_checks: true })
          });
          app()?.toast?.(`Diagnóstico completado: ${Math.round(Number(result.quality?.score || 0) * 100)}%`);
        } else if (issueButton) {
          await request(`/api/v101/issues/${encodeURIComponent(issueButton.dataset.v101Issue)}`, {
            method: 'PUT',
            body: JSON.stringify({ status: issueButton.dataset.status })
          });
          app()?.toast?.('Estado de la incidencia actualizado.');
        } else if (proposalButton) {
          await request(`/api/v101/improvements/proposals/${encodeURIComponent(proposalButton.dataset.v101Proposal)}/decision`, {
            method: 'POST',
            body: JSON.stringify({
              decision: proposalButton.dataset.decision,
              decided_by: 'user',
              note: 'Decisión tomada desde Nexus v101'
            })
          });
          app()?.toast?.('Decisión registrada. No se aplicó ningún cambio automáticamente.');
        }
        root.remove();
        await loadReliability(true);
      } catch (error) {
        app()?.toast?.(sanitizeError(error));
      } finally {
        setLoading(root, false);
      }
    });
  }

  function observeNexus() {
    const panel = document.querySelector('#panelContent');
    if (!panel || state.observer) return;
    state.observer = new MutationObserver(() => {
      if (panel.querySelector('.nexus-hero')) queueMicrotask(() => loadReliability());
    });
    state.observer.observe(panel, { childList: true, subtree: true });
  }

  function init() {
    document.documentElement.dataset.jarvisVersion = '101';
    observeNexus();
    document.addEventListener('click', event => {
      if (event.target.closest('[data-view="nexus"]')) setTimeout(() => loadReliability(), 120);
      if (event.target.closest('#panelRefresh') && document.querySelector('#panelContent .nexus-hero')) {
        setTimeout(() => loadReliability(true), 220);
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  } else {
    init();
  }
})();
