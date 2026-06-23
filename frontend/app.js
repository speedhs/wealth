/* ============================================
   Kalpi Trade Execution — App Logic
   ============================================ */

(function () {
  'use strict';

  // ─── State ──────────────────────────────────────
  const state = {
    mode: 'FIRST_TIME',
    trades: [],
    executing: false,
    currentExecutionId: null,
    pollInterval: null,
    logs: [],
  };

  // ─── DOM References ─────────────────────────────
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  const dom = {
    portfolioId: $('#input-portfolio-id'),
    broker: $('#select-broker'),
    modeToggle: $('#mode-toggle'),
    qtyHeader: $('#qty-header'),
    modeHint: $('#mode-hint'),
    tradeTableBody: $('#trade-table-body'),
    tradeCount: $('#trade-count'),
    btnAddStock: $('#btn-add-stock'),
    btnLoadSample: $('#btn-load-sample'),
    btnExecute: $('#btn-execute'),
    tabTracker: $('#tab-tracker'),
    tabHistory: $('#tab-history'),
    panelTracker: $('#panel-tracker'),
    panelHistory: $('#panel-history'),
    trackerEmpty: $('#tracker-empty'),
    trackerActive: $('#tracker-active'),
    metaStatus: $('#meta-status'),
    metaExecId: $('#meta-exec-id'),
    metaPortfolioId: $('#meta-portfolio-id'),
    metaCreatedAt: $('#meta-created-at'),
    progressCount: $('#progress-count'),
    progressBar: $('#progress-bar'),
    ordersTableBody: $('#orders-table-body'),
    terminalBody: $('#terminal-body'),
    historyEmpty: $('#history-empty'),
    historyList: $('#history-list'),
    toastContainer: $('#toast-container'),
  };

  // ─── Utilities ──────────────────────────────────
  function uuid() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
      const r = (Math.random() * 16) | 0;
      const v = c === 'x' ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    });
  }

  function shortId(id) {
    if (!id) return '—';
    return id.substring(0, 8) + '...';
  }

  function formatTime(dateStr) {
    if (!dateStr) return '—';
    const d = new Date(dateStr);
    return d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
  }

  function formatDateTime(dateStr) {
    if (!dateStr) return '—';
    const d = new Date(dateStr);
    return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }) + ', ' +
      d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: false });
  }

  function now() {
    return new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
  }

  // ─── Toast Notifications ───────────────────────
  function showToast(message, type = 'default') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    dom.toastContainer.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(8px)';
      toast.style.transition = 'all 200ms ease';
      setTimeout(() => toast.remove(), 200);
    }, 3500);
  }

  // ─── Badge HTML ─────────────────────────────────
  function badgeHTML(status) {
    const s = (status || '').toUpperCase();
    let cls = 'badge-pending';
    if (s === 'COMPLETED' || s === 'EXECUTED') cls = 'badge-completed';
    else if (s === 'FAILED') cls = 'badge-failed';
    else if (s === 'PROCESSING') cls = 'badge-processing';
    else if (s === 'PARTIALLY_COMPLETED') cls = 'badge-partially';
    else if (s === 'PENDING') cls = 'badge-pending';
    return `<span class="badge ${cls}"><span class="badge-dot"></span>${s.replace('_', ' ')}</span>`;
  }

  // ─── Mode Toggle ───────────────────────────────
  function initModeToggle() {
    dom.modeToggle.addEventListener('click', (e) => {
      const btn = e.target.closest('.toggle-btn');
      if (!btn) return;
      dom.modeToggle.querySelectorAll('.toggle-btn').forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');
      state.mode = btn.dataset.mode;
      updateModeUI();
    });
  }

  function updateModeUI() {
    if (state.mode === 'REBALANCE') {
      dom.qtyHeader.textContent = 'Adjustment';
      dom.modeHint.style.display = 'block';
    } else {
      dom.qtyHeader.textContent = 'Target Qty';
      dom.modeHint.style.display = 'none';
    }
    // Update qty input types for rebalance (allow negatives)
    dom.tradeTableBody.querySelectorAll('.input-qty').forEach((input) => {
      if (state.mode === 'REBALANCE') {
        input.removeAttribute('min');
        input.placeholder = '+/- qty';
      } else {
        input.setAttribute('min', '1');
        input.placeholder = 'qty';
      }
    });
  }

  // ─── Trade Basket ───────────────────────────────
  function addTradeRow(ticker = '', quantity = '') {
    const idx = state.trades.length;
    state.trades.push({ ticker, quantity });
    const tr = document.createElement('tr');
    tr.dataset.index = idx;
    tr.innerHTML = `
      <td><input type="text" class="input-ticker" value="${ticker}" placeholder="e.g. RELIANCE" spellcheck="false" autocomplete="off" /></td>
      <td><input type="number" class="input-qty" value="${quantity}" placeholder="${state.mode === 'REBALANCE' ? '+/- qty' : 'qty'}" ${state.mode === 'FIRST_TIME' ? 'min="1"' : ''} /></td>
      <td><button type="button" class="btn-remove-row" title="Remove">&times;</button></td>
    `;
    dom.tradeTableBody.appendChild(tr);
    updateTradeCount();

    // Event listeners
    const tickerInput = tr.querySelector('.input-ticker');
    const qtyInput = tr.querySelector('.input-qty');
    const removeBtn = tr.querySelector('.btn-remove-row');

    tickerInput.addEventListener('input', () => {
      state.trades[idx].ticker = tickerInput.value.toUpperCase().trim();
    });
    tickerInput.addEventListener('blur', () => {
      tickerInput.value = tickerInput.value.toUpperCase().trim();
    });
    qtyInput.addEventListener('input', () => {
      state.trades[idx].quantity = qtyInput.value;
    });
    removeBtn.addEventListener('click', () => {
      tr.remove();
      state.trades[idx] = null;
      updateTradeCount();
    });
  }

  function getValidTrades() {
    return state.trades.filter((t) => t && t.ticker && t.quantity !== '' && t.quantity !== null)
      .map((t) => ({
        ticker: t.ticker.toUpperCase(),
        quantity: parseInt(t.quantity, 10),
      }))
      .filter((t) => !isNaN(t.quantity) && (state.mode === 'REBALANCE' || t.quantity > 0));
  }

  function updateTradeCount() {
    const count = getValidTrades().length;
    dom.tradeCount.textContent = `${count} stock${count !== 1 ? 's' : ''}`;
  }

  function loadSampleTrades() {
    // Clear existing
    dom.tradeTableBody.innerHTML = '';
    state.trades = [];

    const samples = [
      { ticker: 'RELIANCE', quantity: 10 },
      { ticker: 'TCS', quantity: 5 },
      { ticker: 'HDFCBANK', quantity: 15 },
      { ticker: 'INFY', quantity: 8 },
      { ticker: 'ICICIBANK', quantity: 12 },
    ];
    samples.forEach((s) => addTradeRow(s.ticker, s.quantity));
  }

  // ─── Tabs ───────────────────────────────────────
  function initTabs() {
    $$('.tab-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        $$('.tab-btn').forEach((b) => b.classList.remove('active'));
        $$('.tab-panel').forEach((p) => p.classList.remove('active'));
        btn.classList.add('active');
        const panel = $(`#panel-${btn.dataset.tab}`);
        if (panel) panel.classList.add('active');

        // Refresh history when switching to history tab
        if (btn.dataset.tab === 'history') {
          loadHistory();
        }
      });
    });
  }

  // ─── Terminal Logging ───────────────────────────
  function addLog(msg, type = 'default') {
    state.logs.push({ time: now(), msg, type });
    const line = document.createElement('div');
    line.className = 'log-line';
    const msgClass = type === 'error' ? 'log-error' : type === 'info' ? 'log-info' : '';
    line.innerHTML = `<span class="log-time">${now()}</span><span class="log-msg ${msgClass}">${escapeHtml(msg)}</span>`;
    dom.terminalBody.appendChild(line);
    dom.terminalBody.scrollTop = dom.terminalBody.scrollHeight;
  }

  function clearLogs() {
    state.logs = [];
    dom.terminalBody.innerHTML = '';
  }

  function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  // ─── Execute Trades ─────────────────────────────
  async function executeTrades() {
    const portfolioId = dom.portfolioId.value.trim();
    if (!portfolioId) {
      showToast('Portfolio ID is required', 'error');
      dom.portfolioId.focus();
      return;
    }

    const trades = getValidTrades();
    if (trades.length === 0) {
      showToast('Add at least one valid trade', 'error');
      return;
    }

    state.executing = true;
    dom.btnExecute.disabled = true;
    dom.btnExecute.innerHTML = '<span class="spinner"></span> Executing...';

    // Switch to tracker tab
    dom.tabTracker.click();

    // Show tracker
    dom.trackerEmpty.style.display = 'none';
    dom.trackerActive.style.display = 'block';

    // Reset tracker UI
    clearLogs();
    dom.ordersTableBody.innerHTML = '';
    dom.progressBar.style.width = '0%';
    dom.progressCount.textContent = '0 / 0';
    dom.metaStatus.innerHTML = badgeHTML('PENDING');
    dom.metaExecId.textContent = '—';
    dom.metaPortfolioId.textContent = shortId(portfolioId);
    dom.metaCreatedAt.textContent = '—';

    addLog('Preparing execution payload...', 'info');

    const payload = {
      portfolio_id: portfolioId,
      broker: dom.broker.value,
      action_type: state.mode,
      trades: trades,
    };

    addLog(`Broker: ${payload.broker} | Mode: ${payload.action_type} | Trades: ${trades.length}`, 'info');

    try {
      addLog('POST /api/portfolio/execute', 'info');

      const res = await fetch('/api/portfolio/execute', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || errData.message || `HTTP ${res.status}`);
      }

      const data = await res.json();
      addLog(`Response: ${data.status} — ${data.message || ''}`, data.status === 'COMPLETED' ? 'info' : 'default');

      if (data.status === 'COMPLETED') {
        // No trades needed
        dom.metaStatus.innerHTML = badgeHTML('COMPLETED');
        dom.metaExecId.textContent = shortId(data.portfolio_execution_id);
        dom.progressBar.style.width = '100%';
        dom.progressCount.textContent = 'Done';
        addLog('Portfolio already matches target. No trades executed.', 'info');
        showToast('Portfolio already at target — no trades needed', 'success');
        resetExecuteButton();
        return;
      }

      // PENDING — start polling
      state.currentExecutionId = data.portfolio_execution_id;
      dom.metaExecId.textContent = shortId(data.portfolio_execution_id);
      addLog(`Execution ID: ${data.portfolio_execution_id}`);
      addLog('Starting status polling...');

      startPolling(data.portfolio_execution_id);

    } catch (err) {
      addLog(`Error: ${err.message}`, 'error');
      showToast(err.message, 'error');
      resetExecuteButton();
    }
  }

  // ─── Polling ────────────────────────────────────
  function startPolling(executionId) {
    // Clear any existing interval
    if (state.pollInterval) clearInterval(state.pollInterval);

    // Immediately fetch once
    pollExecution(executionId);

    // Then poll every 2 seconds
    state.pollInterval = setInterval(() => {
      pollExecution(executionId);
    }, 2000);
  }

  function stopPolling() {
    if (state.pollInterval) {
      clearInterval(state.pollInterval);
      state.pollInterval = null;
    }
  }

  async function pollExecution(executionId) {
    try {
      const res = await fetch(`/api/portfolio/execution/${executionId}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      updateTrackerUI(data);

      // Stop polling on terminal states
      const terminalStates = ['COMPLETED', 'FAILED', 'PARTIALLY_COMPLETED'];
      if (terminalStates.includes(data.status)) {
        stopPolling();
        resetExecuteButton();

        if (data.status === 'COMPLETED') {
          addLog('All orders executed successfully.');
          showToast('Execution completed successfully', 'success');
        } else if (data.status === 'FAILED') {
          addLog('Execution failed.', 'error');
          showToast('Execution failed', 'error');
        } else {
          addLog('Execution partially completed — some orders failed.', 'error');
          showToast('Execution partially completed', 'error');
        }
      }
    } catch (err) {
      addLog(`Poll error: ${err.message}`, 'error');
    }
  }

  function updateTrackerUI(data) {
    // Status badge
    dom.metaStatus.innerHTML = badgeHTML(data.status);
    dom.metaExecId.textContent = shortId(data.id);
    dom.metaPortfolioId.textContent = shortId(data.portfolio_id);
    dom.metaCreatedAt.textContent = formatTime(data.created_at);

    // Progress
    const total = data.total_orders || 0;
    const completed = data.completed_orders || 0;
    const pct = total > 0 ? Math.round((completed / total) * 100) : 0;
    dom.progressBar.style.width = `${pct}%`;
    dom.progressCount.textContent = `${completed} / ${total}`;

    // Orders table
    if (data.orders && data.orders.length > 0) {
      dom.ordersTableBody.innerHTML = data.orders.map((order) => {
        const actionClass = (order.action || '').toUpperCase() === 'BUY' ? 'action-buy' : 'action-sell';
        const brokerId = order.broker_order_id ? `<span class="mono">${shortId(order.broker_order_id)}</span>` : '<span class="text-muted">—</span>';
        const details = order.error_message
          ? `<span class="error-text" title="${escapeHtml(order.error_message)}">${escapeHtml(order.error_message)}</span>`
          : '<span class="text-muted">—</span>';

        return `
          <tr>
            <td class="ticker-cell">${escapeHtml(order.ticker || '')}</td>
            <td class="${actionClass}">${(order.action || '').toUpperCase()}</td>
            <td class="mono">${order.quantity}</td>
            <td>${badgeHTML(order.status)}</td>
            <td>${brokerId}</td>
            <td>${details}</td>
          </tr>
        `;
      }).join('');
    }
  }

  function resetExecuteButton() {
    state.executing = false;
    dom.btnExecute.disabled = false;
    dom.btnExecute.innerHTML = 'Execute Trades';
  }

  // ─── History ────────────────────────────────────
  async function loadHistory() {
    try {
      const res = await fetch('/api/portfolio/executions');
      if (!res.ok) return;
      const data = await res.json();

      // Handle both array and object with items/executions
      const executions = Array.isArray(data) ? data : (data.items || data.executions || []);

      if (executions.length === 0) {
        dom.historyEmpty.style.display = 'block';
        dom.historyList.style.display = 'none';
        return;
      }

      dom.historyEmpty.style.display = 'none';
      dom.historyList.style.display = 'flex';

      dom.historyList.innerHTML = executions.map((exec) => {
        const ordersText = exec.total_orders != null ? `${exec.completed_orders || 0}/${exec.total_orders} orders` : '';
        return `
          <div class="history-item" data-execution-id="${exec.id}">
            <span class="history-item-id">${shortId(exec.id)}</span>
            <div class="history-item-info">
              <span class="history-item-portfolio">${exec.portfolio_id || '—'}</span>
            </div>
            ${badgeHTML(exec.status)}
            <div>
              <div class="history-item-orders">${ordersText}</div>
              <div class="history-item-time">${formatDateTime(exec.created_at)}</div>
            </div>
          </div>
        `;
      }).join('');

      // Click handler for history items
      dom.historyList.querySelectorAll('.history-item').forEach((item) => {
        item.addEventListener('click', () => {
          const execId = item.dataset.executionId;
          viewExecution(execId);
        });
      });

    } catch (err) {
      // Silently fail — history is non-critical
    }
  }

  async function viewExecution(executionId) {
    // Switch to tracker tab
    dom.tabTracker.click();
    dom.trackerEmpty.style.display = 'none';
    dom.trackerActive.style.display = 'block';

    clearLogs();
    addLog(`Loading execution ${shortId(executionId)}...`, 'info');

    try {
      const res = await fetch(`/api/portfolio/execution/${executionId}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      updateTrackerUI(data);
      addLog(`Loaded execution — status: ${data.status}`, 'info');

      // If still processing, start polling
      if (data.status === 'PROCESSING' || data.status === 'PENDING') {
        state.currentExecutionId = executionId;
        startPolling(executionId);
      }

    } catch (err) {
      addLog(`Error loading execution: ${err.message}`, 'error');
      showToast('Failed to load execution details', 'error');
    }
  }

  // ─── Init ───────────────────────────────────────
  function init() {
    // Generate a UUID on load
    dom.portfolioId.value = uuid();

    // Add initial empty trade row
    addTradeRow();

    // Mode toggle
    initModeToggle();

    // Tabs
    initTabs();

    // Add stock button
    dom.btnAddStock.addEventListener('click', () => addTradeRow());

    // Load sample button
    dom.btnLoadSample.addEventListener('click', loadSampleTrades);

    // Execute button
    dom.btnExecute.addEventListener('click', () => {
      if (!state.executing) executeTrades();
    });

    // Listen for trade input changes to update count
    dom.tradeTableBody.addEventListener('input', updateTradeCount);

    // Load history on startup
    loadHistory();
  }

  // Boot
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
