document.addEventListener('DOMContentLoaded', () => {
    const navButtons = document.querySelectorAll('.nav-btn');
    const tabPanes = document.querySelectorAll('.tab-pane');
    const statusBadge = document.getElementById('global-status-badge');
    const statTotal = document.getElementById('stat-total');
    const statDone = document.getElementById('stat-done');
    const statPending = document.getElementById('stat-pending');
    const statFailed = document.getElementById('stat-failed');
    const statImages = document.getElementById('stat-images');
    const btnRunBatch = document.getElementById('btn-run-batch');
    const btnStopBatch = document.getElementById('btn-stop-batch');
    const btnResetFailed = document.getElementById('btn-reset-failed');
    const btnLaunchLogin = document.getElementById('btn-launch-login');
    const wsIndicator = document.getElementById('ws-indicator');
    const terminalOutput = document.getElementById('terminal-output');
    const btnClearLogs = document.getElementById('btn-clear-logs');
    const chkAutoScroll = document.getElementById('chk-autoscroll');
    const vncIframe = document.getElementById('vnc-iframe');
    const vncDirectLink = document.getElementById('vnc-direct-link');
    const btnRefreshVnc = document.getElementById('btn-refresh-vnc');
    const addPromptForm = document.getElementById('add-prompt-form');
    const inputNewPrompt = document.getElementById('input-new-prompt');
    const tableBody = document.getElementById('prompts-table-body');
    const filterButtons = document.querySelectorAll('.filter-btn');
    const galleryGrid = document.getElementById('gallery-grid');

    let currentFilter = 'all';
    let promptsData = [];

    navButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            const targetTab = btn.getAttribute('data-tab');
            navButtons.forEach(b => b.classList.remove('active'));
            tabPanes.forEach(p => p.classList.remove('active'));
            btn.classList.add('active');
            document.getElementById(targetTab).classList.add('active');
            if (targetTab === 'tab-prompts') loadPrompts();
            if (targetTab === 'tab-gallery') loadGallery();
        });
    });

    const host = window.location.hostname || 'localhost';
    const vncUrl = `http://${host}:6080/vnc.html?autoconnect=true&resize=scale`;
    if (vncDirectLink) vncDirectLink.href = vncUrl;
    if (btnRefreshVnc) {
        btnRefreshVnc.addEventListener('click', () => {
            if (vncIframe) vncIframe.src = vncUrl;
        });
    }

    async function updateStatus() {
        try {
            const res = await fetch('/api/status');
            if (!res.ok) return;
            const data = await res.json();
            statusBadge.textContent = data.status;
            statusBadge.className = `status-pill ${data.status.toLowerCase()}`;
            if (data.status === 'Running') {
                btnRunBatch.disabled = true;
                btnStopBatch.disabled = false;
                btnLaunchLogin.disabled = true;
            } else if (data.status === 'Stopping') {
                btnRunBatch.disabled = true;
                btnStopBatch.disabled = true;
                btnLaunchLogin.disabled = true;
            } else {
                btnRunBatch.disabled = false;
                btnStopBatch.disabled = true;
                btnLaunchLogin.disabled = false;
            }
            statTotal.textContent = data.total_prompts;
            statDone.textContent = data.done_count;
            statPending.textContent = data.pending_count;
            statFailed.textContent = data.failed_count;
            statImages.textContent = data.image_count;
        } catch (e) {
            console.error('Status fetch error:', e);
        }
    }

    setInterval(updateStatus, 3000);
    updateStatus();

    let ws = null;
    function connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/logs`;
        ws = new WebSocket(wsUrl);

        ws.onopen = () => {
            wsIndicator.className = 'dot online';
            appendLog('[SYSTEM] WebSocket connected to log stream.', 'system');
        };

        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.type === 'history') {
                terminalOutput.innerHTML = '';
                data.logs.forEach(log => appendLog(log));
            } else if (data.type === 'log') {
                appendLog(data.message);
            }
            if (data.status) {
                statusBadge.textContent = data.status;
                statusBadge.className = `status-pill ${data.status.toLowerCase()}`;
            }
        };

        ws.onclose = () => {
            wsIndicator.className = 'dot offline';
            setTimeout(connectWebSocket, 4000);
        };

        ws.onerror = (err) => {
            console.error('WebSocket error:', err);
            ws.close();
        };
    }

    function appendLog(message, cls = '') {
        const line = document.createElement('div');
        line.className = `log-line ${cls}`;
        if (message.includes('ERROR') || message.includes('Failed')) line.classList.add('error');
        if (message.includes('Done!') || message.includes('Acceptable image found')) line.classList.add('success');
        if (message.includes('[SYSTEM]')) line.classList.add('system');
        line.textContent = message;
        terminalOutput.appendChild(line);
        if (chkAutoScroll.checked) {
            terminalOutput.scrollTop = terminalOutput.scrollHeight;
        }
    }

    btnClearLogs.addEventListener('click', () => {
        terminalOutput.innerHTML = '<div class="log-line system">[SYSTEM] Terminal cleared.</div>';
    });

    connectWebSocket();

    btnRunBatch.addEventListener('click', async () => {
        const res = await fetch('/api/run', { method: 'POST' });
        const data = await res.json();
        appendLog(`[ACTION] ${data.message}`, 'system');
        updateStatus();
    });

    btnStopBatch.addEventListener('click', async () => {
        const res = await fetch('/api/stop', { method: 'POST' });
        const data = await res.json();
        appendLog(`[ACTION] ${data.message}`, 'system');
        updateStatus();
    });

    btnResetFailed.addEventListener('click', async () => {
        const res = await fetch('/api/prompts/reset-failed', { method: 'POST' });
        const data = await res.json();
        appendLog(`[ACTION] ${data.message || 'Reset failed prompts.'}`, 'system');
        updateStatus();
        loadPrompts();
    });

    btnLaunchLogin.addEventListener('click', async () => {
        const res = await fetch('/api/login', { method: 'POST' });
        const data = await res.json();
        appendLog(`[ACTION] ${data.message}`, 'system');
        updateStatus();
    });

    async function loadPrompts() {
        try {
            const res = await fetch('/api/prompts');
            if (!res.ok) return;
            promptsData = await res.json();
            renderPromptsTable();
        } catch (e) {
            console.error('Error loading prompts:', e);
        }
    }

    function renderPromptsTable() {
        const filtered = promptsData.filter(p => {
            if (currentFilter === 'all') return true;
            if (currentFilter === 'pending') return !p.status;
            return p.status.toLowerCase() === currentFilter;
        });

        if (filtered.length === 0) {
            tableBody.innerHTML = `<tr><td colspan="7" class="empty-state">No prompts found matching filter "${currentFilter}".</td></tr>`;
            return;
        }

        tableBody.innerHTML = filtered.map(p => {
            const statusClass = p.status ? p.status.toLowerCase() : 'pending';
            const statusLabel = p.status || 'Pending';
            return `
                <tr>
                    <td>${p.id + 1}</td>
                    <td><strong>${escapeHtml(p.prompt)}</strong></td>
                    <td><span class="badge ${statusClass}">${statusLabel}</span></td>
                    <td>${p.score ? `${p.score}/10` : '-'}</td>
                    <td>${p.filename ? `<a href="/output_images/${p.filename}" target="_blank" class="vnc-link">${p.filename}</a>` : '-'}</td>
                    <td>${p.date || '-'}</td>
                    <td>
                        <button class="btn btn-primary btn-sm btn-run-single" data-id="${p.id}">▶ Run</button>
                        <button class="btn btn-danger btn-sm btn-del-prompt" data-id="${p.id}">🗑</button>
                    </td>
                </tr>
            `;
        }).join('');

        document.querySelectorAll('.btn-run-single').forEach(b => {
            b.addEventListener('click', async () => {
                const id = parseInt(b.getAttribute('data-id'));
                const res = await fetch('/api/run-single', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ id })
                });
                const data = await res.json();
                appendLog(`[ACTION] ${data.message}`, 'system');
                updateStatus();
            });
        });

        document.querySelectorAll('.btn-del-prompt').forEach(b => {
            b.addEventListener('click', async () => {
                const id = parseInt(b.getAttribute('data-id'));
                if (!confirm('Are you sure you want to delete this prompt?')) return;
                const res = await fetch('/api/prompts/delete', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ id })
                });
                if (res.ok) loadPrompts();
            });
        });
    }

    filterButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            filterButtons.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentFilter = btn.getAttribute('data-filter');
            renderPromptsTable();
        });
    });

    addPromptForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const text = inputNewPrompt.value.trim();
        if (!text) return;
        const res = await fetch('/api/prompts/add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ prompt: text })
        });
        if (res.ok) {
            inputNewPrompt.value = '';
            loadPrompts();
            updateStatus();
        }
    });

    async function loadGallery() {
        try {
            const res = await fetch('/api/gallery');
            if (!res.ok) return;
            const images = await res.json();
            if (images.length === 0) {
                galleryGrid.innerHTML = `<div class="empty-state card" style="grid-column: 1/-1;">No generated images found yet in output_images/.</div>`;
                return;
            }
            galleryGrid.innerHTML = images.map(img => `
                <div class="gallery-card">
                    <div class="gallery-img-wrapper">
                        <img src="${img.url}" alt="${escapeHtml(img.prompt)}" class="gallery-img" loading="lazy">
                        ${img.score !== 'N/A' ? `<span class="score-tag">Score: ${img.score}/10</span>` : ''}
                    </div>
                    <div class="gallery-info">
                        <p class="gallery-prompt" title="${escapeHtml(img.prompt)}">${escapeHtml(img.prompt)}</p>
                        <div class="gallery-footer">
                            <span>${img.size_kb} KB</span>
                            <a href="${img.url}" download="${img.filename}" class="btn btn-outline btn-sm">Download ⬇</a>
                        </div>
                    </div>
                </div>
            `).join('');
        } catch (e) {
            console.error('Gallery fetch error:', e);
        }
    }

    function escapeHtml(str) {
        return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }
});
