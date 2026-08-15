document.addEventListener('DOMContentLoaded', () => {
    // Tab Navigation
    const navButtons = document.querySelectorAll('.nav-btn');
    const tabPanes = document.querySelectorAll('.tab-pane');

    navButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            const targetTab = btn.getAttribute('data-tab');
            navButtons.forEach(b => b.classList.remove('active'));
            tabPanes.forEach(p => p.classList.remove('active'));
            btn.classList.add('active');
            document.getElementById(targetTab).classList.add('active');

            if (targetTab === 'tab-prompts') loadPrompts();
            if (targetTab === 'tab-gallery') loadGallery();
            if (targetTab === 'tab-settings') loadSettings();
        });
    });

    // Elements
    const globalStatusBadge = document.getElementById('global-status-badge');
    const statTotal = document.getElementById('stat-total');
    const statDone = document.getElementById('stat-done');
    const statPending = document.getElementById('stat-pending');
    const statFailed = document.getElementById('stat-failed');
    const statImages = document.getElementById('stat-images');

    const btnRunBatch = document.getElementById('btn-run-batch');
    const btnStopBatch = document.getElementById('btn-stop-batch');
    const btnResetFailed = document.getElementById('btn-reset-failed');
    const btnLaunchLogin = document.getElementById('btn-launch-login');
    const btnClearLogs = document.getElementById('btn-clear-logs');
    const chkAutoScroll = document.getElementById('chk-autoscroll');
    const terminalOutput = document.getElementById('terminal-output');
    const wsIndicator = document.getElementById('ws-indicator');

    const addPromptForm = document.getElementById('add-prompt-form');
    const inputNewPrompt = document.getElementById('input-new-prompt');
    const tableBody = document.getElementById('prompts-table-body');
    const filterButtons = document.querySelectorAll('.filter-btn');

    const galleryGrid = document.getElementById('gallery-grid');
    const settingsForm = document.getElementById('settings-form');
    const inputReplicateToken = document.getElementById('setting-replicate-token');
    const inputScoreThreshold = document.getElementById('setting-score-threshold');
    const inputMaxRetries = document.getElementById('setting-max-retries');
    const btnToggleToken = document.getElementById('btn-toggle-token');
    const settingsToast = document.getElementById('settings-toast');

    let currentFilter = 'all';
    let promptsData = [];
    let ws = null;

    // ── WebSocket Log Stream ──────────────────────────────────────────────────
    function connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/logs`;

        ws = new WebSocket(wsUrl);

        ws.onopen = () => {
            wsIndicator.className = 'dot online';
        };

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.type === 'history') {
                    terminalOutput.innerHTML = '';
                    data.logs.forEach(log => appendLog(log));
                    updateStatusPill(data.status);
                } else if (data.type === 'log') {
                    appendLog(data.message);
                    if (data.status) updateStatusPill(data.status);
                }
            } catch (e) {
                appendLog(event.data);
            }
        };

        ws.onclose = () => {
            wsIndicator.className = 'dot offline';
            setTimeout(connectWebSocket, 3000);
        };

        ws.onerror = (err) => {
            wsIndicator.className = 'dot offline';
        };
    }

    function appendLog(text, type = 'normal') {
        const line = document.createElement('div');
        line.className = `log-line ${type}`;
        line.textContent = text;
        terminalOutput.appendChild(line);

        if (chkAutoScroll.checked) {
            terminalOutput.scrollTop = terminalOutput.scrollHeight;
        }
    }

    btnClearLogs.addEventListener('click', () => {
        terminalOutput.innerHTML = '<div class="log-line system">[SYSTEM] Terminal logs cleared.</div>';
    });

    // ── API Actions & Status Polling ─────────────────────────────────────────
    async function updateStatus() {
        try {
            const res = await fetch('/api/status');
            if (!res.ok) return;
            const data = await res.json();

            statTotal.textContent = data.total_prompts;
            statDone.textContent = data.done_count;
            statPending.textContent = data.pending_count;
            statFailed.textContent = data.failed_count;
            statImages.textContent = data.image_count;

            updateStatusPill(data.status);

            if (data.status === 'Running') {
                btnRunBatch.disabled = true;
                btnStopBatch.disabled = false;
            } else {
                btnRunBatch.disabled = false;
                btnStopBatch.disabled = true;
            }
        } catch (e) {
            console.error('Error fetching status:', e);
        }
    }

    function updateStatusPill(status) {
        globalStatusBadge.textContent = status;
        globalStatusBadge.className = 'status-pill ' + (status ? status.toLowerCase() : 'idle');
    }

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
        appendLog(`[ACTION] Reset ${data.reset_count} failed prompt(s).`, 'system');
        updateStatus();
        loadPrompts();
    });

    btnLaunchLogin.addEventListener('click', async () => {
        const res = await fetch('/api/login', { method: 'POST' });
        const data = await res.json();
        appendLog(`[ACTION] ${data.message}`, 'system');
        updateStatus();
    });

    // ── Prompts Table ────────────────────────────────────────────────────────
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

    // ── Settings Logic ───────────────────────────────────────────────────────
    const inputCliproxyKey = document.getElementById('setting-cliproxy-key');
    const inputCliproxyUrl = document.getElementById('setting-cliproxy-url');
    const inputCliproxyModel = document.getElementById('setting-cliproxy-model');
    const inputOpenaiKey = document.getElementById('setting-openai-key');

    async function loadSettings() {
        try {
            const res = await fetch('/api/settings');
            if (!res.ok) return;
            const data = await res.json();
            if (inputCliproxyKey) inputCliproxyKey.value = data.CLIPROXY_API_KEY || '';
            if (inputCliproxyUrl) inputCliproxyUrl.value = data.CLIPROXY_BASE_URL || 'https://cli-proxy-api.femioja.cfd';
            if (inputCliproxyModel) inputCliproxyModel.value = data.CLIPROXY_MODEL || 'gemini-3.5-flash-low';
            if (inputOpenaiKey) inputOpenaiKey.value = data.OPENAI_API_KEY || '';
            if (inputReplicateToken) inputReplicateToken.value = data.REPLICATE_API_TOKEN || '';
            if (inputScoreThreshold) inputScoreThreshold.value = data.SCORE_THRESHOLD || 6;
            if (inputMaxRetries) inputMaxRetries.value = data.MAX_RETRIES || 2;
        } catch (e) {
            console.error('Error loading settings:', e);
        }
    }

    document.querySelectorAll('.toggle-password').forEach(btn => {
        btn.addEventListener('click', () => {
            const targetId = btn.getAttribute('data-target');
            const targetInput = document.getElementById(targetId);
            if (targetInput) {
                if (targetInput.type === 'password') {
                    targetInput.type = 'text';
                    btn.textContent = 'Hide';
                } else {
                    targetInput.type = 'password';
                    btn.textContent = 'Show';
                }
            }
        });
    });

    if (settingsForm) {
        settingsForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const payload = {
                CLIPROXY_API_KEY: inputCliproxyKey ? inputCliproxyKey.value.trim() : '',
                CLIPROXY_BASE_URL: inputCliproxyUrl ? inputCliproxyUrl.value.trim() : '',
                CLIPROXY_MODEL: inputCliproxyModel ? inputCliproxyModel.value.trim() : '',
                OPENAI_API_KEY: inputOpenaiKey ? inputOpenaiKey.value.trim() : '',
                REPLICATE_API_TOKEN: inputReplicateToken ? inputReplicateToken.value.trim() : '',
                SCORE_THRESHOLD: parseInt(inputScoreThreshold.value) || 6,
                MAX_RETRIES: parseInt(inputMaxRetries.value) || 2
            };
            const res = await fetch('/api/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            if (res.ok) {
                settingsToast.textContent = '✓ Settings saved successfully!';
                setTimeout(() => { settingsToast.textContent = ''; }, 4000);
            }
        });
    }

    function escapeHtml(str) {
        return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    // Init
    connectWebSocket();
    updateStatus();
    setInterval(updateStatus, 5000);
});
