document.addEventListener('DOMContentLoaded', () => {
    // Nav & Tabs
    const navButtons = document.querySelectorAll('.nav-btn');
    const tabPanes = document.querySelectorAll('.tab-pane');

    navButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            const targetTab = btn.getAttribute('data-tab');
            navButtons.forEach(b => b.classList.remove('active'));
            tabPanes.forEach(p => p.classList.remove('active'));
            btn.classList.add('active');
            const pane = document.getElementById(targetTab);
            if (pane) pane.classList.add('active');

            if (targetTab === 'tab-prompts') loadPrompts();
            if (targetTab === 'tab-gallery') loadGallery();
            if (targetTab === 'tab-settings') loadSettings();
        });
    });

    // Elements
    const statusBadge = document.getElementById('global-status-badge');
    const statTotal = document.getElementById('stat-total');
    const statDone = document.getElementById('stat-done');
    const statPending = document.getElementById('stat-pending');
    const statFailed = document.getElementById('stat-failed');
    const statImages = document.getElementById('stat-images');

    const btnRunBatch = document.getElementById('btn-run-batch');
    const btnStopBatch = document.getElementById('btn-stop-batch');
    const btnResetFailed = document.getElementById('btn-reset-failed');
    const btnResetAll = document.getElementById('btn-reset-all');
    const btnLaunchLogin = document.getElementById('btn-launch-login');
    const wsIndicator = document.getElementById('ws-indicator');
    const terminalOutput = document.getElementById('terminal-output');
    const btnClearLogs = document.getElementById('btn-clear-logs');
    const chkAutoScroll = document.getElementById('chk-autoscroll');

    const addPromptForm = document.getElementById('add-prompt-form');
    const inputNewPrompt = document.getElementById('input-new-prompt');
    const tableBody = document.getElementById('prompts-table-body');
    const filterButtons = document.querySelectorAll('.filter-btn');
    const galleryGrid = document.getElementById('gallery-grid');

    const chkSelectAll = document.getElementById('chk-select-all');
    const btnDeleteSelected = document.getElementById('btn-delete-selected');
    const selectedCountSpan = document.getElementById('selected-count');
    const btnClearAllPrompts = document.getElementById('btn-clear-all-prompts');

    // Settings Elements
    const settingsForm = document.getElementById('settings-form');
    const inputCliproxyKey = document.getElementById('setting-cliproxy-key');
    const inputCliproxyUrl = document.getElementById('setting-cliproxy-url');
    const inputCliproxyModel = document.getElementById('setting-cliproxy-model');
    const inputOpenaiKey = document.getElementById('setting-openai-key');
    const inputReplicateToken = document.getElementById('setting-replicate-token');
    const inputScoreThreshold = document.getElementById('setting-score-threshold');
    const inputMaxRetries = document.getElementById('setting-max-retries');
    const settingsToast = document.getElementById('settings-toast');

    let currentFilter = 'all';
    let promptsData = [];
    let ws = null;

    // ── Status Polling ────────────────────────────────────────────────────────
    async function updateStatus() {
        try {
            const res = await fetch('/api/status');
            if (!res.ok) return;
            const data = await res.json();
            if (statusBadge) {
                statusBadge.textContent = data.status;
                statusBadge.className = `status-pill ${data.status.toLowerCase()}`;
            }

            if (data.status === 'Running') {
                if (btnRunBatch) btnRunBatch.disabled = true;
                if (btnStopBatch) btnStopBatch.disabled = false;
                if (btnLaunchLogin) btnLaunchLogin.disabled = true;
            } else if (data.status === 'Stopping') {
                if (btnRunBatch) btnRunBatch.disabled = true;
                if (btnStopBatch) btnStopBatch.disabled = true;
                if (btnLaunchLogin) btnLaunchLogin.disabled = true;
            } else {
                if (btnRunBatch) btnRunBatch.disabled = false;
                if (btnStopBatch) btnStopBatch.disabled = true;
                if (btnLaunchLogin) btnLaunchLogin.disabled = false;
            }

            if (statTotal) statTotal.textContent = data.total_prompts;
            if (statDone) statDone.textContent = data.done_count;
            if (statPending) statPending.textContent = data.pending_count;
            if (statFailed) statFailed.textContent = data.failed_count;
            if (statImages) statImages.textContent = data.image_count;
        } catch (e) {
            console.error('Status fetch error:', e);
        }
    }

    // ── WebSocket Log Stream ──────────────────────────────────────────────────
    function connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/logs`;
        ws = new WebSocket(wsUrl);

        ws.onopen = () => {
            if (wsIndicator) wsIndicator.className = 'dot online';
        };

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.type === 'history') {
                    if (terminalOutput) terminalOutput.innerHTML = '';
                    data.logs.forEach(log => appendLog(log));
                } else if (data.type === 'log') {
                    appendLog(data.message);
                }
            } catch (e) {
                appendLog(event.data);
            }
        };

        ws.onclose = () => {
            if (wsIndicator) wsIndicator.className = 'dot offline';
            setTimeout(connectWebSocket, 3000);
        };

        ws.onerror = () => {
            if (wsIndicator) wsIndicator.className = 'dot offline';
        };
    }

    function appendLog(text, type = 'normal') {
        if (!terminalOutput) return;
        const line = document.createElement('div');
        line.className = `log-line ${type}`;
        line.textContent = text;
        terminalOutput.appendChild(line);

        if (chkAutoScroll && chkAutoScroll.checked) {
            terminalOutput.scrollTop = terminalOutput.scrollHeight;
        }
    }

    if (btnClearLogs) {
        btnClearLogs.addEventListener('click', () => {
            if (terminalOutput) terminalOutput.innerHTML = '<div class="log-line system">[SYSTEM] Terminal logs cleared.</div>';
        });
    }

    // ── Action Buttons ────────────────────────────────────────────────────────
    if (btnRunBatch) {
        btnRunBatch.addEventListener('click', async () => {
            const res = await fetch('/api/run', { method: 'POST' });
            const data = await res.json();
            appendLog(`[ACTION] ${data.message}`, 'system');
            updateStatus();
        });
    }

    if (btnStopBatch) {
        btnStopBatch.addEventListener('click', async () => {
            const res = await fetch('/api/stop', { method: 'POST' });
            const data = await res.json();
            appendLog(`[ACTION] ${data.message}`, 'system');
            updateStatus();
        });
    }

    if (btnResetFailed) {
        btnResetFailed.addEventListener('click', async () => {
            const res = await fetch('/api/prompts/reset-failed', { method: 'POST' });
            const data = await res.json();
            appendLog(`[ACTION] Reset ${data.reset_count} failed prompt(s).`, 'system');
            updateStatus();
            loadPrompts();
        });
    }

    if (btnResetAll) {
        btnResetAll.addEventListener('click', async () => {
            if (!confirm('Are you sure you want to reset ALL prompts back to Pending status?')) return;
            const res = await fetch('/api/prompts/reset-all', { method: 'POST' });
            const data = await res.json();
            appendLog(`[ACTION] Reset ${data.reset_count} prompt(s) back to Pending.`, 'system');
            updateStatus();
            loadPrompts();
        });
    }

    if (btnLaunchLogin) {
        btnLaunchLogin.addEventListener('click', async () => {
            const res = await fetch('/api/login', { method: 'POST' });
            const data = await res.json();
            appendLog(`[ACTION] ${data.message}`, 'system');
            updateStatus();
        });
    }

    // ── Prompts Database & Bulk Operations ───────────────────────────────────
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

    function updateSelectionState() {
        const checkedBoxes = document.querySelectorAll('.chk-select-prompt:checked');
        const count = checkedBoxes.length;
        if (selectedCountSpan) selectedCountSpan.textContent = count;
        if (btnDeleteSelected) btnDeleteSelected.disabled = (count === 0);

        const allBoxes = document.querySelectorAll('.chk-select-prompt');
        if (chkSelectAll && allBoxes.length > 0) {
            chkSelectAll.checked = (checkedBoxes.length === allBoxes.length);
        }
    }

    if (chkSelectAll) {
        chkSelectAll.addEventListener('change', () => {
            const isChecked = chkSelectAll.checked;
            document.querySelectorAll('.chk-select-prompt').forEach(chk => {
                chk.checked = isChecked;
            });
            updateSelectionState();
        });
    }

    if (btnDeleteSelected) {
        btnDeleteSelected.addEventListener('click', async () => {
            const checkedBoxes = document.querySelectorAll('.chk-select-prompt:checked');
            const ids = Array.from(checkedBoxes).map(cb => parseInt(cb.getAttribute('data-id')));
            if (ids.length === 0) return;

            if (!confirm(`Are you sure you want to delete ${ids.length} selected prompt(s)?`)) return;

            const res = await fetch('/api/prompts/delete-bulk', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ids })
            });

            if (res.ok) {
                if (chkSelectAll) chkSelectAll.checked = false;
                loadPrompts();
                updateStatus();
            }
        });
    }

    if (btnClearAllPrompts) {
        btnClearAllPrompts.addEventListener('click', async () => {
            if (!confirm('🚨 WARNING: Are you sure you want to delete ALL prompts from prompts.csv database?')) return;

            const res = await fetch('/api/prompts/clear-all', { method: 'POST' });
            if (res.ok) {
                if (chkSelectAll) chkSelectAll.checked = false;
                loadPrompts();
                updateStatus();
            }
        });
    }

    function renderPromptsTable() {
        if (!tableBody) return;
        const filtered = promptsData.filter(p => {
            if (currentFilter === 'all') return true;
            if (currentFilter === 'pending') return !p.status;
            return p.status.toLowerCase() === currentFilter;
        });

        if (filtered.length === 0) {
            tableBody.innerHTML = `<tr><td colspan="8" class="empty-state">No prompts found matching filter "${currentFilter}".</td></tr>`;
            updateSelectionState();
            return;
        }

        tableBody.innerHTML = filtered.map(p => {
            const statusClass = p.status ? p.status.toLowerCase() : 'pending';
            const statusLabel = p.status || 'Pending';
            const reasonBtn = p.reason ? `<button class="btn btn-outline btn-sm btn-show-reason" style="margin-left: 6px; padding: 2px 6px; font-size: 11px;" data-reason="${escapeHtml(p.reason)}" data-prompt="${escapeHtml(p.prompt)}">🔍 Why?</button>` : '';
            return `
                <tr>
                    <td style="text-align: center;"><input type="checkbox" class="chk-select-prompt" data-id="${p.id}"></td>
                    <td>${p.id + 1}</td>
                    <td><strong>${escapeHtml(p.prompt)}</strong></td>
                    <td><span class="badge ${statusClass}">${statusLabel}</span></td>
                    <td>${p.score ? `${p.score}/10` : '-'}${reasonBtn}</td>
                    <td>${p.filename ? `<a href="/output_images/${p.filename}" target="_blank" class="vnc-link">${p.filename}</a>` : '-'}</td>
                    <td>${p.date || '-'}</td>
                    <td>
                        <button class="btn btn-primary btn-sm btn-run-single" data-id="${p.id}">▶ Run</button>
                        <button class="btn btn-danger btn-sm btn-del-prompt" data-id="${p.id}">🗑</button>
                    </td>
                </tr>
            `;
        }).join('');

        document.querySelectorAll('.btn-show-reason').forEach(b => {
            b.addEventListener('click', () => {
                const promptText = b.getAttribute('data-prompt');
                const reasonText = b.getAttribute('data-reason');
                alert(`🤖 Vision LLM Evaluation Feedback:\n\nPrompt:\n"${promptText}"\n\nDetailed Reasoning:\n${reasonText}`);
            });
        });

        document.querySelectorAll('.chk-select-prompt').forEach(chk => {
            chk.addEventListener('change', updateSelectionState);
        });

        updateSelectionState();

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

    if (addPromptForm) {
        addPromptForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const text = inputNewPrompt.value.trim();
            if (!text) return;

            const lines = text.split('\n').map(l => l.trim()).filter(l => l.length > 0);
            if (lines.length === 0) return;

            let addedCount = 0;
            for (const promptLine of lines) {
                const res = await fetch('/api/prompts/add', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ prompt: promptLine })
                });
                if (res.ok) addedCount++;
            }

            inputNewPrompt.value = '';
            appendLog(`[ACTION] Successfully added ${addedCount} prompt(s) to database.`, 'system');
            loadPrompts();
            updateStatus();
        });
    }

    async function loadGallery() {
        if (!galleryGrid) return;
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
                if (settingsToast) {
                    settingsToast.textContent = '✓ Settings saved successfully!';
                    setTimeout(() => { settingsToast.textContent = ''; }, 4000);
                }
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
