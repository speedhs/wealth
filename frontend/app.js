let currentExecutionMode = 'FIRST_TIME';
let activeExecutionId = null;
let pollingInterval = null;

// On document load
document.addEventListener("DOMContentLoaded", () => {
    // Set a random portfolio UUID for testing convenience
    document.getElementById("portfolio-id").value = generateUUID();
    
    // Add default initial rows
    loadSamplePortfolio();
    
    // Check if there's any active execution stored in localStorage
    const savedJobId = localStorage.getItem("active_execution_id");
    if (savedJobId) {
        startTrackingJob(savedJobId);
    }
});

function generateUUID() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        var r = Math.random() * 16 | 0, v = c == 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
}

function setExecutionMode(mode) {
    currentExecutionMode = mode;
    
    // Update active visual class
    document.getElementById("mode-first-time").classList.toggle("active", mode === 'FIRST_TIME');
    document.getElementById("mode-rebalance").classList.toggle("active", mode === 'REBALANCE');
    
    // Update all actions in the table if it's First-Time
    const actionSelects = document.querySelectorAll(".row-action");
    actionSelects.forEach(select => {
        if (mode === 'FIRST_TIME') {
            select.value = 'BUY';
            select.disabled = true;
            
            // Convert any negative quantities to positive
            const qtyInput = select.closest("tr").querySelector(".row-qty");
            if (qtyInput && parseInt(qtyInput.value) < 0) {
                qtyInput.value = Math.abs(parseInt(qtyInput.value));
            }
        } else {
            select.disabled = false;
        }
    });
    
    updateBasketCount();
}

function addTradeRow(ticker = '', action = 'BUY', quantity = 10) {
    const tbody = document.getElementById("trades-input-body");
    const row = document.createElement("tr");
    
    const isFirstTime = currentExecutionMode === 'FIRST_TIME';
    
    row.innerHTML = `
        <td>
            <input type="text" class="row-ticker" placeholder="e.g. INFY" value="${ticker}" oninput="this.value = this.value.toUpperCase()">
        </td>
        <td>
            <select class="row-action" ${isFirstTime ? 'disabled' : ''}>
                <option value="BUY" ${action === 'BUY' ? 'selected' : ''}>BUY</option>
                <option value="SELL" ${action === 'SELL' ? 'selected' : ''}>SELL</option>
                <option value="REBALANCE" ${action === 'REBALANCE' ? 'selected' : ''}>REBALANCE</option>
            </select>
        </td>
        <td>
            <input type="number" class="row-qty" value="${quantity}" placeholder="Qty">
        </td>
        <td>
            <button class="delete-row" onclick="deleteRow(this)">×</button>
        </td>
    `;
    
    tbody.appendChild(row);
    updateBasketCount();
}

function deleteRow(btn) {
    btn.closest("tr").remove();
    updateBasketCount();
}

function updateBasketCount() {
    const rows = document.querySelectorAll("#trades-input-body tr");
    document.getElementById("basket-count").textContent = `${rows.length} stock${rows.length !== 1 ? 's' : ''}`;
}

function loadSamplePortfolio() {
    const tbody = document.getElementById("trades-input-body");
    tbody.innerHTML = "";
    
    if (currentExecutionMode === 'FIRST_TIME') {
        addTradeRow("RELIANCE", "BUY", 15);
        addTradeRow("TCS", "BUY", 8);
        addTradeRow("HDFCBANK", "BUY", 25);
        addTradeRow("INFY", "BUY", 12);
    } else {
        addTradeRow("RELIANCE", "REBALANCE", 5);       // adjust +5 shares
        addTradeRow("TCS", "SELL", 4);                 // exit 4 shares
        addTradeRow("HDFCBANK", "REBALANCE", -10);     // adjust -10 shares (resolves to SELL)
        addTradeRow("WIPRO", "BUY", 50);               // brand new stock buy
        addTradeRow("FAIL", "BUY", 10);                // This will fail intentionally for demo
    }
}

// Switches tab panes
function switchTab(tabName) {
    document.getElementById("tab-tracker").classList.toggle("active", tabName === 'tracker');
    document.getElementById("tab-history").classList.toggle("active", tabName === 'history');
    
    document.getElementById("pane-tracker").classList.toggle("hidden", tabName !== 'tracker');
    document.getElementById("pane-history").classList.toggle("hidden", tabName !== 'history');
    
    if (tabName === 'history') {
        loadExecutionHistory();
    }
}

// Submit to FastAPI Backend
async function submitPortfolioExecution() {
    const portfolioId = document.getElementById("portfolio-id").value.trim();
    const broker = document.getElementById("broker-select").value;
    
    if (!portfolioId) {
        alert("Please enter a Portfolio UUID.");
        return;
    }
    
    const rows = document.querySelectorAll("#trades-input-body tr");
    if (rows.length === 0) {
        alert("Portfolio trade basket is empty. Add at least one trade.");
        return;
    }
    
    const trades = [];
    let validationError = null;
    
    rows.forEach((row, i) => {
        const ticker = row.querySelector(".row-ticker").value.trim();
        const action = row.querySelector(".row-action").value;
        const qtyStr = row.querySelector(".row-qty").value;
        
        if (!ticker) {
            validationError = `Row ${i + 1} has empty ticker symbol.`;
        }
        
        const qty = parseInt(qtyStr);
        if (isNaN(qty)) {
            validationError = `Row ${i + 1} (${ticker || 'Stock'}) has an invalid quantity.`;
        }
        
        trades.push({
            ticker: ticker,
            action: action,
            quantity: qty
        });
    });
    
    if (validationError) {
        alert(validationError);
        return;
    }
    
    const payload = {
        portfolio_id: portfolioId,
        broker: broker,
        action_type: currentExecutionMode,
        trades: trades
    };
    
    const executeBtn = document.getElementById("execute-btn");
    executeBtn.disabled = true;
    executeBtn.textContent = "Validating and Enqueuing...";
    
    try {
        const response = await fetch("/api/portfolio/execute", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify(payload)
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.detail || "Server error while launching execution.");
        }
        
        // Show tracking area
        document.getElementById("no-active-job").classList.add("hidden");
        document.getElementById("job-details-area").classList.remove("hidden");
        
        if (data.status === "COMPLETED") {
            // Already in desired state
            const badge = document.getElementById("overall-job-status");
            badge.className = "badge badge-executed";
            badge.textContent = "COMPLETED";
            
            document.getElementById("progress-bar-fill").style.width = "100%";
            document.getElementById("progress-percentage").textContent = "100% (0/0)";
            
            document.getElementById("lbl-job-id").textContent = data.portfolio_execution_id;
            document.getElementById("lbl-portfolio-id").textContent = portfolioId;
            
            const tbody = document.getElementById("execution-orders-body");
            tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--success); font-weight: 600; padding: 2rem;">✓ Portfolio is already in the desired state. No trades required.</td></tr>`;
            
            const consoleLogs = document.getElementById("console-logs");
            consoleLogs.textContent = `================================================================================\n` +
                                      `🚨 PORTFOLIO STATUS REPORT 🚨\n` +
                                      `Portfolio ID     : ${portfolioId}\n` +
                                      `Job ID           : ${data.portfolio_execution_id}\n` +
                                      `Status           : ✅ NO ACTION REQUIRED\n` +
                                      `Message          : ${data.message}\n` +
                                      `================================================================================`;
            
            if (pollingInterval) clearInterval(pollingInterval);
            localStorage.removeItem("active_execution_id");
            switchTab('tracker');
        } else {
            // Start tracking
            startTrackingJob(data.portfolio_execution_id);
            switchTab('tracker');
        }
        
    } catch (error) {
        alert(`RMS / Validation Error:\n\n${error.message}`);
    } finally {
        executeBtn.disabled = false;
        executeBtn.textContent = "🚀 Execute Trades in Single Click";
    }
}

function startTrackingJob(jobId) {
    activeExecutionId = jobId;
    localStorage.setItem("active_execution_id", jobId);
    
    // Clear logs area
    const consoleLogs = document.getElementById("console-logs");
    consoleLogs.textContent = `Connecting to execution engine tracker...\nJob ID: ${jobId}\nListening to queues...\n`;
    
    // Reset progress bar
    document.getElementById("progress-bar-fill").style.width = "0%";
    document.getElementById("progress-percentage").textContent = "0% (0/0)";
    
    // Set headers
    document.getElementById("lbl-job-id").textContent = jobId;
    document.getElementById("lbl-portfolio-id").textContent = document.getElementById("portfolio-id").value;
    
    // Clear active status badge
    const badge = document.getElementById("overall-job-status");
    badge.className = "badge badge-processing";
    badge.textContent = "Processing";
    
    // Poll endpoints
    if (pollingInterval) clearInterval(pollingInterval);
    pollJobStatus(); // Initial run
    pollingInterval = setInterval(pollJobStatus, 800);
}

async function pollJobStatus() {
    if (!activeExecutionId) return;
    
    try {
        const response = await fetch(`/api/portfolio/execution/${activeExecutionId}`);
        if (!response.ok) {
            if (response.status === 404) {
                // Job hasn't hit db yet, waiting
                return;
            }
            throw new Error("Failed to fetch execution status.");
        }
        
        const data = await response.json();
        updateTrackerUI(data);
        
        // Check if finished
        const terminalStates = ["COMPLETED", "FAILED", "PARTIALLY_COMPLETED"];
        if (terminalStates.includes(data.status)) {
            clearInterval(pollingInterval);
            pollingInterval = null;
            localStorage.removeItem("active_execution_id");
            
            // Format log report in console
            renderReportLogs(data);
        }
    } catch (error) {
        console.error("Polling error:", error);
    }
}

function updateTrackerUI(data) {
    // 1. Update overall status badge
    const badge = document.getElementById("overall-job-status");
    badge.textContent = data.status.replace("_", " ");
    
    if (data.status === "COMPLETED") {
        badge.className = "badge badge-executed";
    } else if (data.status === "FAILED") {
        badge.className = "badge badge-failed";
    } else if (data.status === "PARTIALLY_COMPLETED") {
        badge.className = "badge badge-warning";
    } else {
        badge.className = "badge badge-processing";
    }
    
    // 2. Update Progress Bar
    const total = data.total_orders;
    const completed = data.completed_orders;
    const pct = total > 0 ? Math.round((completed / total) * 100) : 0;
    
    document.getElementById("progress-bar-fill").style.width = `${pct}%`;
    document.getElementById("progress-percentage").textContent = `${pct}% (${completed}/${total})`;
    
    // 3. Update orders list
    const tbody = document.getElementById("execution-orders-body");
    tbody.innerHTML = "";
    
    data.orders.forEach(order => {
        const tr = document.createElement("tr");
        
        let statusBadge = "";
        if (order.status === "EXECUTED") {
            statusBadge = '<span class="badge badge-executed">Executed</span>';
        } else if (order.status === "FAILED") {
            statusBadge = '<span class="badge badge-failed">Failed</span>';
        } else if (order.status === "PENDING") {
            statusBadge = '<span class="badge badge-pending">Pending</span>';
        } else {
            statusBadge = `<span class="badge badge-processing">${order.status}</span>`;
        }
        
        tr.innerHTML = `
            <td style="font-weight:600;">${order.ticker}</td>
            <td>${order.action}</td>
            <td>${order.quantity}</td>
            <td>${statusBadge}</td>
            <td style="font-family:monospace; font-size:0.8rem;">${order.broker_order_id || '-'}</td>
            <td style="font-size:0.8rem; color:${order.status === 'FAILED' ? 'var(--danger)' : 'var(--text-muted)'}">
                ${order.error_message || (order.status === 'EXECUTED' ? 'Order processed successfully' : 'Queued...')}
            </td>
        `;
        
        tbody.appendChild(tr);
    });
    
    // Highlight UI card area
    document.getElementById("no-active-job").classList.add("hidden");
    document.getElementById("job-details-area").classList.remove("hidden");
}

function renderReportLogs(data) {
    const consoleLogs = document.getElementById("console-logs");
    
    const successList = data.orders.filter(o => o.status === 'EXECUTED');
    const failedList = data.orders.filter(o => o.status === 'FAILED');
    
    let report = `================================================================================\n`;
    report += `🚨 PORTFOLIO TRADE EXECUTION REPORT 🚨\n`;
    report += `Execution Job ID : ${data.id}\n`;
    report += `Portfolio ID     : ${data.portfolio_id}\n`;
    report += `Status           : ${data.status}\n`;
    report += `Summary          : ${successList.length}/${data.total_orders} Orders Succeeded\n`;
    report += `================================================================================\n\n`;
    
    if (successList.length > 0) {
        report += `✓ SUCCESSFUL TRADES:\n`;
        successList.forEach(o => {
            report += `  - BUY ${o.quantity} shares of ${o.ticker} (Broker Order ID: ${o.broker_order_id})\n`;
        });
        report += `\n`;
    }
    
    if (failedList.length > 0) {
        report += `✗ FAILED / REJECTED TRADES:\n`;
        failedList.forEach(o => {
            report += `  - BUY ${o.quantity} shares of ${o.ticker} - Reason: ${o.error_message}\n`;
        });
        report += `\n`;
    }
    
    report += `================================================================================\n`;
    report += `Engine Core: Log notification output generated. Completed in async queues.`;
    
    consoleLogs.textContent = report;
}

// Fetch history from DB
async function loadExecutionHistory() {
    const container = document.getElementById("history-list-container");
    container.innerHTML = `<div style="padding: 2rem 0; text-align: center; color: var(--text-muted);">Loading historical records...</div>`;
    
    try {
        const response = await fetch("/api/portfolio/executions");
        if (!response.ok) throw new Error("Could not load history.");
        
        const data = await response.json();
        
        if (data.length === 0) {
            container.innerHTML = `
                <div style="padding: 3rem 1rem; text-align: center; color: var(--text-muted);">
                    <p>No trade execution logs found in Postgres.</p>
                </div>`;
            return;
        }
        
        container.innerHTML = "";
        data.forEach(job => {
            const div = document.createElement("div");
            div.className = "history-item";
            div.onclick = () => {
                // Load details of this historical job in tracker
                activeExecutionId = job.id;
                document.getElementById("portfolio-id").value = job.portfolio_id;
                pollJobStatus();
                switchTab('tracker');
            };
            
            let badgeClass = "badge-processing";
            if (job.status === "COMPLETED") badgeClass = "badge-executed";
            if (job.status === "FAILED") badgeClass = "badge-failed";
            if (job.status === "PARTIALLY_COMPLETED") badgeClass = "badge-warning";
            
            const dateStr = new Date(job.created_at).toLocaleString();
            
            div.innerHTML = `
                <div class="history-header">
                    <strong style="font-family:monospace; font-size:0.9rem;">Job: ${job.id.substring(0, 8)}...</strong>
                    <span class="badge ${badgeClass}">${job.status.replace("_", " ")}</span>
                </div>
                <div class="history-meta">
                    <span>Portfolio: ${job.portfolio_id.substring(0, 8)}...</span>
                    <span>Trades: ${job.completed_orders}/${job.total_orders} done</span>
                    <span>Date: ${dateStr}</span>
                </div>
            `;
            
            container.appendChild(div);
        });
        
    } catch (error) {
        container.innerHTML = `<div style="padding: 2rem 0; text-align: center; color: var(--danger);">${error.message}</div>`;
    }
}
