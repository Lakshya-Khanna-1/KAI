(function () {
  'use strict';

  // Fallback RFC4122 v4 UUID generator for insecure HTTP IP contexts (e.g. Tailscale IP)
  function generateUUID() {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
      try {
        return crypto.randomUUID();
      } catch (e) {
        // Fallback if randomUUID fails
      }
    }
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
      const r = (Math.random() * 16) | 0;
      const v = c === 'x' ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    });
  }

  // State management
  const state = {
    conversationId: localStorage.getItem('kai_conv_id') || generateUUID(),
    apiToken: localStorage.getItem('kai_api_token') || '',
    activeView: 'chat',
    isStreaming: false
  };

  localStorage.setItem('kai_conv_id', state.conversationId);

  // Helper to safely get DOM elements dynamically
  const el = (id) => document.getElementById(id);
  const queryAll = (selector) => document.querySelectorAll(selector);

  let isInitialized = false;

  // Initialize App
  function init() {
    if (isInitialized) return;
    isInitialized = true;

    registerServiceWorker();
    setupEventListeners();

    const tokenInput = el('api-token-input');
    if (tokenInput && state.apiToken) {
      tokenInput.value = state.apiToken;
    }

    fetchSystemHealth(true);
  }

  // Service Worker & Web Push Registration
  function registerServiceWorker() {
    try {
      if ('serviceWorker' in navigator && (window.isSecureContext || location.hostname === 'localhost' || location.hostname === '127.0.0.1')) {
        navigator.serviceWorker.register('/sw.js').then((reg) => {
          console.log('Service Worker registered successfully:', reg.scope);
        }).catch((err) => {
          console.warn('Service Worker registration skipped/failed:', err);
        });
      }
    } catch (err) {
      console.warn('Service Worker not supported or blocked in this context:', err);
    }
  }

  // Setup Event Listeners
  function setupEventListeners() {
    // Nav buttons
    queryAll('.nav-btn').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        const targetView = btn.getAttribute('data-view');
        switchView(targetView);
      });
    });

    // Chat send button
    const btnSend = el('btn-send');
    if (btnSend) {
      btnSend.addEventListener('click', (e) => {
        e.preventDefault();
        sendMessage();
      });
    }

    // Chat textarea key listener
    const chatInput = el('chat-input');
    if (chatInput) {
      chatInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          sendMessage();
        }
      });

      chatInput.addEventListener('input', () => {
        chatInput.style.height = 'auto';
        chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + 'px';
      });
    }

    // Tasks & Reminders buttons
    const btnAddTask = el('btn-add-task');
    if (btnAddTask) btnAddTask.addEventListener('click', (e) => { e.preventDefault(); addNewTask(); });

    const btnRefreshTasks = el('btn-refresh-tasks');
    if (btnRefreshTasks) btnRefreshTasks.addEventListener('click', (e) => { e.preventDefault(); loadTasks(); });

    const btnRefreshReminders = el('btn-refresh-reminders');
    if (btnRefreshReminders) btnRefreshReminders.addEventListener('click', (e) => { e.preventDefault(); loadReminders(); });

    // Settings buttons
    const btnSaveToken = el('btn-save-token');
    if (btnSaveToken) {
      btnSaveToken.addEventListener('click', (e) => {
        e.preventDefault();
        const tokenInput = el('api-token-input');
        if (tokenInput) {
          state.apiToken = tokenInput.value.trim();
          localStorage.setItem('kai_api_token', state.apiToken);
          alert('API Token saved successfully.');
          fetchSystemHealth();
        }
      });
    }

    const btnSubPush = el('btn-sub-push');
    if (btnSubPush) btnSubPush.addEventListener('click', (e) => { e.preventDefault(); requestPushPermission(); });

    // Onboarding buttons
    ['btn-start-onboarding', 'btn-welcome-onboarding', 'btn-settings-onboarding'].forEach((id) => {
      const btn = el(id);
      if (btn) btn.addEventListener('click', (e) => { e.preventDefault(); startOnboardingInterview(); });
    });

    // Memory buttons
    const btnSearchMemory = el('btn-search-memory');
    if (btnSearchMemory) {
      btnSearchMemory.addEventListener('click', (e) => {
        e.preventDefault();
        const input = el('memory-search-input');
        loadMemoryFacts(input ? input.value : '');
      });
    }
    const btnRefreshMemory = el('btn-refresh-memory');
    if (btnRefreshMemory) btnRefreshMemory.addEventListener('click', (e) => { e.preventDefault(); loadMemoryFacts(); });

    // Roadmap buttons
    const btnPreviewRoadmap = el('btn-preview-roadmap');
    if (btnPreviewRoadmap) btnPreviewRoadmap.addEventListener('click', (e) => { e.preventDefault(); previewRoadmap(); });

    const btnImportRoadmap = el('btn-import-roadmap');
    if (btnImportRoadmap) btnImportRoadmap.addEventListener('click', (e) => { e.preventDefault(); previewRoadmap(); });

    const btnRefreshRoadmap = el('btn-refresh-roadmap');
    if (btnRefreshRoadmap) btnRefreshRoadmap.addEventListener('click', (e) => { e.preventDefault(); loadActiveRoadmap(); });

    // Modal buttons
    const btnCloseModal = el('btn-close-modal');
    if (btnCloseModal) btnCloseModal.addEventListener('click', (e) => { e.preventDefault(); closeRoadmapModal(); });

    const btnCancelModal = el('btn-cancel-modal');
    if (btnCancelModal) btnCancelModal.addEventListener('click', (e) => { e.preventDefault(); closeRoadmapModal(); });

    const btnConfirmModal = el('btn-confirm-modal');
    if (btnConfirmModal) btnConfirmModal.addEventListener('click', (e) => { e.preventDefault(); confirmImportRoadmap(); });

    // Theme toggle
    const btnThemeToggle = el('btn-theme-toggle');
    if (btnThemeToggle) {
      btnThemeToggle.addEventListener('click', (e) => {
        e.preventDefault();
        document.body.classList.toggle('light-theme');
        btnThemeToggle.textContent = document.body.classList.contains('light-theme') ? '☀️' : '🌙';
      });
    }

    // Global Event Delegation fallback for maximum reliability
    document.addEventListener('click', (e) => {
      const navBtn = e.target.closest('.nav-btn');
      if (navBtn) {
        const view = navBtn.getAttribute('data-view');
        if (view) switchView(view);
      }

      const obBtn = e.target.closest('#btn-start-onboarding, #btn-welcome-onboarding, #btn-settings-onboarding');
      if (obBtn) {
        e.preventDefault();
        startOnboardingInterview();
      }
    });
  }

  // View Switcher
  function switchView(viewName) {
    state.activeView = viewName;

    queryAll('.nav-btn').forEach((btn) => {
      btn.classList.toggle('active', btn.getAttribute('data-view') === viewName);
    });

    queryAll('.view').forEach((v) => {
      v.classList.toggle('active', v.id === `view-${viewName}`);
    });

    if (viewName === 'tasks') loadTasks();
    if (viewName === 'reminders') loadReminders();
    if (viewName === 'memory') loadMemoryFacts();
    if (viewName === 'roadmap') loadActiveRoadmap();
    if (viewName === 'settings') {
      fetchSystemHealth();
      loadProfileInSettings();
    }
  }

  // Memory View Functions
  async function loadMemoryFacts(query = '') {
    const list = el('memory-facts-list');
    if (!list) return;
    try {
      let resp;
      if (query.trim()) {
        resp = await apiFetch('/memory/search', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query: query.trim() })
        });
      } else {
        resp = await apiFetch('/memory');
      }
      const facts = await resp.json();
      if (!facts || facts.length === 0) {
        list.innerHTML = '<div class="empty-state">No facts or memories found.</div>';
        return;
      }
      list.innerHTML = '';
      facts.forEach((f) => {
        const isSuperseded = !!f.superseded_by;
        const card = document.createElement('div');
        card.className = 'item-card';
        if (isSuperseded) card.style.opacity = '0.5';
        card.innerHTML = `
          <div>
            <div class="item-title">${escapeHtml(f.subject)} ${escapeHtml(f.predicate)} = "${escapeHtml(f.value)}"</div>
            <div class="item-meta">Created: ${f.created_at ? new Date(f.created_at).toLocaleString() : 'N/A'} ${isSuperseded ? '| [SUPERSEDED]' : ''}</div>
          </div>
          ${!isSuperseded ? `<button class="btn-secondary" onclick="forgetFact('${f.id}')">Forget</button>` : ''}
        `;
        list.appendChild(card);
      });
    } catch (err) {
      list.innerHTML = `<div class="empty-state">Error loading memory: ${err.message}</div>`;
    }
  }

  window.forgetFact = async function(factId) {
    try {
      await apiFetch('/memory/forget', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ fact_id_or_query: factId })
      });
      loadMemoryFacts();
    } catch (err) {
      alert('Error forgetting fact: ' + err.message);
    }
  };

  // Roadmap View Functions
  let currentPreviewData = null;

  async function loadActiveRoadmap() {
    const container = el('active-roadmap-container');
    if (!container) return;
    try {
      const resp = await apiFetch('/roadmap/active');
      const data = await resp.json();
      const rm = data.roadmap;
      if (!rm) {
        container.innerHTML = '<div class="empty-state">No active roadmap found. Paste one below to import!</div>';
        return;
      }
      let html = `<div style="background: rgba(255,255,255,0.03); border: 1px solid var(--border); border-radius: 12px; padding: 16px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
          <h3 style="margin: 0;">${escapeHtml(rm.name)}</h3>
          <span class="badge" style="background: rgba(24,144,255,0.2); color: #1890ff; padding: 4px 8px; border-radius: 12px; font-size: 0.8rem;">Active</span>
        </div>`;

      rm.phases.forEach((p) => {
        html += `<div style="margin-top: 14px; border-top: 1px solid rgba(255,255,255,0.1); padding-top: 10px;">
          <h4 style="margin: 0 0 8px 0; color: var(--accent, #1890ff);">${escapeHtml(p.name)}</h4>`;
        p.topics.forEach((t) => {
          const statusIcon = t.status === 'completed' ? '✅' : t.status === 'in_progress' ? '⏳' : '⚪';
          html += `<div style="display: flex; justify-content: space-between; align-items: center; background: rgba(0,0,0,0.15); padding: 8px 12px; border-radius: 6px; margin-bottom: 6px;">
            <div>
              <span>${statusIcon} <strong>${escapeHtml(t.title)}</strong></span>
              <span style="font-size: 0.8rem; opacity: 0.7; margin-left: 10px;">(${t.hours_done}/${t.est_hours} hrs)</span>
            </div>
            <select onchange="updateTopicStatus('${t.id}', this.value)" style="background: var(--bg); color: inherit; border: 1px solid var(--border); border-radius: 4px; padding: 2px 6px; font-size: 0.8rem;">
              <option value="not_started" ${t.status === 'not_started' ? 'selected' : ''}>Not Started</option>
              <option value="in_progress" ${t.status === 'in_progress' ? 'selected' : ''}>In Progress</option>
              <option value="completed" ${t.status === 'completed' ? 'selected' : ''}>Completed</option>
            </select>
          </div>`;
        });
        html += `</div>`;
      });
      html += `</div>`;
      container.innerHTML = html;
    } catch (err) {
      container.innerHTML = `<div class="empty-state">Error loading roadmap: ${err.message}</div>`;
    }
  }

  window.updateTopicStatus = async function(topicId, newStatus) {
    try {
      await apiFetch('/roadmap/topic/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ topic_id: topicId, status: newStatus })
      });
      loadActiveRoadmap();
    } catch (err) {
      alert('Error updating topic status: ' + err.message);
    }
  };

  async function previewRoadmap() {
    const text = el('roadmap-paste-input').value;
    if (!text.trim()) { alert('Please paste roadmap text first.'); return; }
    try {
      const resp = await apiFetch('/roadmap/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source_text: text })
      });
      const res = await resp.json();
      currentPreviewData = res.preview;
      showRoadmapModal(res.preview);
    } catch (err) {
      alert('Error previewing roadmap: ' + err.message);
    }
  }

  async function confirmImportRoadmap() {
    const text = el('roadmap-paste-input').value;
    if (!text.trim()) { alert('Please paste roadmap text first.'); return; }
    try {
      const resp = await apiFetch('/roadmap/import', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source_text: text, confirm: true })
      });
      const res = await resp.json();
      if (res.status === 'success') {
        alert('Roadmap successfully imported and saved!');
        closeRoadmapModal();
        el('roadmap-paste-input').value = '';
        loadActiveRoadmap();
      }
    } catch (err) {
      alert('Error importing roadmap: ' + err.message);
    }
  }

  function showRoadmapModal(preview) {
    const modal = el('roadmap-modal');
    const title = el('modal-roadmap-title');
    const body = el('modal-roadmap-body');
    if (!modal || !body) return;

    title.textContent = `Preview: ${preview.roadmap_name}`;
    let html = `<div style="margin-bottom: 12px; font-size: 0.9rem; background: rgba(24,144,255,0.1); padding: 10px; border-radius: 6px;">
      <strong>Summary:</strong> ${preview.total_phases} Phases | ${preview.total_topics} Topics | ~${preview.total_est_hours} Total Estimated Hours
    </div>`;

    if (preview.is_reimport && preview.diff) {
      html += `<div style="margin-bottom: 12px; font-size: 0.85rem; background: rgba(255,193,7,0.1); border: 1px solid rgba(255,193,7,0.3); padding: 8px; border-radius: 6px;">
        <strong>Diff (Re-import):</strong>
        <div style="color:#52c41a">+ Added: ${preview.diff.added.join(', ') || 'None'}</div>
        <div style="color:#1890ff">= Retained (hours kept): ${preview.diff.retained.join(', ') || 'None'}</div>
        <div style="color:#ff4d4f">- Archived: ${preview.diff.removed.join(', ') || 'None'}</div>
      </div>`;
    }

    preview.parsed_tree.phases.forEach((p) => {
      html += `<div style="margin-top: 10px;">
        <strong style="color: var(--accent);">${escapeHtml(p.name)}</strong>
        <ul style="margin: 4px 0 10px 18px; padding: 0; font-size: 0.85rem;">`;
      p.topics.forEach((t) => {
        html += `<li>${escapeHtml(t.title)} (${t.est_hours} hrs)</li>`;
      });
      html += `</ul></div>`;
    });

    body.innerHTML = html;
    modal.style.display = 'flex';
  }

  function closeRoadmapModal() {
    const modal = el('roadmap-modal');
    if (modal) modal.style.display = 'none';
  }


  async function startOnboardingInterview() {
    try {
      await apiFetch('/onboarding', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'reset' })
      });
      switchView('chat');
      const chatInput = el('chat-input');
      if (chatInput) {
        chatInput.value = "Hi KAI, let's start the onboarding interview so you can get to know me!";
        sendMessage();
      }
    } catch (err) {
      alert('Error starting onboarding interview: ' + err.message);
    }
  }

  async function loadProfileInSettings() {
    const box = el('user-profile-box');
    if (!box) return;
    try {
      const resp = await apiFetch('/onboarding/profile');
      const prof = await resp.json();
      if (!prof || Object.keys(prof).length === 0) {
        box.innerHTML = '<i>No profile facts saved yet. Click "Start Onboarding Interview" to begin!</i>';
        return;
      }
      box.innerHTML = Object.entries(prof).map(([k, v]) => `<div style="padding: 2px 0;"><strong>${escapeHtml(k)}:</strong> ${escapeHtml(String(v))}</div>`).join('');
    } catch (err) {
      box.innerHTML = `<span style="color:red">Error loading profile: ${err.message}</span>`;
    }
  }

  // API Fetch Helper with Authorization
  async function apiFetch(url, options = {}) {
    options.headers = options.headers || {};
    if (state.apiToken) {
      options.headers['Authorization'] = `Bearer ${state.apiToken}`;
    }
    const resp = await fetch(url, options);
    if (resp.status === 401) {
      const statusDot = el('status-dot');
      if (statusDot) {
        statusDot.className = 'status-indicator offline';
        statusDot.textContent = 'Auth Required';
      }
      throw new Error('Unauthorized - Please configure your API Token in Settings.');
    }
    return resp;
  }

  // Chat Streaming Logic
  async function sendMessage() {
    const chatInput = el('chat-input');
    const btnSend = el('btn-send');
    if (!chatInput) return;

    const text = chatInput.value.trim();
    if (!text || state.isStreaming) return;

    chatInput.value = '';
    chatInput.style.height = 'auto';

    // Append User Message
    appendMessage('user', text);

    state.isStreaming = true;
    if (btnSend) btnSend.disabled = true;

    // Create Assistant Message container
    const msgCard = appendMessage('assistant', '');
    const contentDiv = msgCard.querySelector('.msg-content');

    try {
      const resp = await apiFetch('/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          conversation_id: state.conversationId,
          message: text
        })
      });

      const reader = resp.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const dataStr = line.slice(6).trim();
            if (!dataStr) continue;
            try {
              const event = JSON.parse(dataStr);
              handleSSEEvent(event, contentDiv);
            } catch (err) {
              console.warn('Malformed SSE data:', dataStr);
            }
          }
        }
      }
    } catch (err) {
      console.error('Streaming error:', err);
      contentDiv.innerHTML += `<br><span style="color:var(--danger, #ff4d4f)">Error: ${err.message}</span>`;
      if (err.message.includes('Unauthorized')) {
        switchView('settings');
      }
    } finally {
      state.isStreaming = false;
      if (btnSend) btnSend.disabled = false;
    }
  }

  // Handle SSE Events
  function handleSSEEvent(event, contentDiv) {
    const chatMessages = el('chat-messages');
    if (event.type === 'token') {
      contentDiv.innerHTML += escapeHtml(event.content).replace(/\n/g, '<br>');
      if (chatMessages) chatMessages.scrollTop = chatMessages.scrollHeight;
    } else if (event.type === 'tool_start') {
      const chip = document.createElement('div');
      chip.className = 'tool-chip';
      chip.innerHTML = `
        <div class="tool-chip-header" onclick="this.parentElement.classList.toggle('open')">
          <span>⚙️ Running ${escapeHtml(event.tool_name)}...</span>
          <span>▼</span>
        </div>
        <div class="tool-chip-body">
          <strong>Arguments:</strong><br>${escapeHtml(JSON.stringify(event.args, null, 2))}
        </div>
      `;
      contentDiv.appendChild(chip);
      if (chatMessages) chatMessages.scrollTop = chatMessages.scrollHeight;
    } else if (event.type === 'tool_result') {
      const chips = contentDiv.querySelectorAll('.tool-chip');
      const lastChip = chips[chips.length - 1];
      if (lastChip) {
        const header = lastChip.querySelector('.tool-chip-header span');
        if (header) header.textContent = `✅ ${escapeHtml(event.tool_name)} completed`;
        const body = lastChip.querySelector('.tool-chip-body');
        if (body) {
          body.innerHTML += `<br><br><strong>Result:</strong><br>${escapeHtml(JSON.stringify(event.result, null, 2))}`;
        }
      }
    }
  }

  // Append Message Card
  function appendMessage(role, text) {
    const chatMessages = el('chat-messages');
    const card = document.createElement('div');
    card.className = `message ${role}-msg`;
    const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    card.innerHTML = `
      <div class="msg-header">
        <span class="sender-name">${role === 'user' ? 'You' : 'KAI'}</span>
        <span class="msg-time">${timeStr}</span>
      </div>
      <div class="msg-content">${escapeHtml(text).replace(/\n/g, '<br>')}</div>
    `;

    if (chatMessages) {
      chatMessages.appendChild(card);
      chatMessages.scrollTop = chatMessages.scrollHeight;
    }
    return card;
  }

  // Tasks View Logic
  async function loadTasks() {
    const tasksList = el('tasks-list');
    if (!tasksList) return;
    tasksList.innerHTML = '<div class="empty-state">Loading tasks...</div>';
    try {
      const resp = await apiFetch('/tasks');
      const tasks = await resp.json();
      if (!tasks || tasks.length === 0) {
        tasksList.innerHTML = '<div class="empty-state">No active tasks found.</div>';
        return;
      }
      tasksList.innerHTML = '';
      tasks.forEach((t) => {
        const card = document.createElement('div');
        card.className = 'item-card';
        const dueStr = t.due_at ? new Date(t.due_at).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' }) : null;
        const metaParts = [];
        if (dueStr) metaParts.push(`📅 Due: ${dueStr}`);
        metaParts.push(`Priority: ${t.priority}`);
        if (t.recurrence_rule) metaParts.push(`🔁 ${t.recurrence_rule}`);

        card.innerHTML = `
          <div style="flex: 1;">
            <div class="item-title">${escapeHtml(t.title)}</div>
            <div class="item-meta">${metaParts.join(' | ')}</div>
            ${t.notes ? `<div style="font-size: 0.82rem; color: var(--text-muted); margin-top: 4px;">${escapeHtml(t.notes)}</div>` : ''}
          </div>
          <div style="display: flex; gap: 6px; align-items: center;">
            <button class="btn-secondary" style="background: rgba(82, 196, 26, 0.15); color: #52c41a; border-color: rgba(82, 196, 26, 0.3);" onclick="completeTask('${t.id}')">✓ Done</button>
            <button class="btn-secondary" style="background: rgba(255, 77, 79, 0.15); color: #ff4d4f; border-color: rgba(255, 77, 79, 0.3);" onclick="deleteTask('${t.id}')">🗑️</button>
          </div>
        `;
        tasksList.appendChild(card);
      });
    } catch (err) {
      tasksList.innerHTML = `<div class="empty-state">Error: ${err.message}</div>`;
    }
  }

  async function addNewTask() {
    const newTaskTitle = el('new-task-title');
    if (!newTaskTitle) return;
    const title = newTaskTitle.value.trim();
    if (!title) return;
    try {
      await apiFetch('/tasks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title, priority: 'normal' })
      });
      newTaskTitle.value = '';
      loadTasks();
    } catch (err) {
      alert('Error adding task: ' + err.message);
    }
  }

  window.completeTask = async function (taskId) {
    try {
      const resp = await apiFetch(`/tasks/${taskId}/complete`, { method: 'POST' });
      const completedTask = await resp.json();
      if (completedTask.recurrence_rule) {
        console.log('Recurring task completed. Next instance scheduled.');
      }
      loadTasks();
    } catch (err) {
      alert('Error completing task: ' + err.message);
    }
  };

  window.deleteTask = async function (taskId) {
    if (!confirm('Are you sure you want to delete this task?')) return;
    try {
      await apiFetch(`/tasks/${taskId}`, { method: 'DELETE' });
      loadTasks();
    } catch (err) {
      alert('Error deleting task: ' + err.message);
    }
  };

  // Reminders View Logic
  async function loadReminders() {
    const remindersList = el('reminders-list');
    if (!remindersList) return;
    remindersList.innerHTML = '<div class="empty-state">Loading reminders...</div>';
    try {
      const resp = await apiFetch('/reminders');
      const reminders = await resp.json();
      if (!reminders || reminders.length === 0) {
        remindersList.innerHTML = '<div class="empty-state">No pending reminders found.</div>';
        return;
      }
      remindersList.innerHTML = '';
      reminders.forEach((r) => {
        const fireAtStr = r.fire_at ? new Date(r.fire_at).toLocaleString() : 'N/A';
        const card = document.createElement('div');
        card.className = 'item-card';
        card.innerHTML = `
          <div>
            <div class="item-title">${escapeHtml(r.text)}</div>
            <div class="item-meta">Fires at: ${fireAtStr} | Status: ${r.status} | Priority: ${r.priority}</div>
          </div>
          <button class="btn-secondary" onclick="cancelReminder('${r.id}')">Cancel</button>
        `;
        remindersList.appendChild(card);
      });
    } catch (err) {
      remindersList.innerHTML = `<div class="empty-state">Error: ${err.message}</div>`;
    }
  }

  window.cancelReminder = async function (reminderId) {
    try {
      await apiFetch(`/reminders/${reminderId}`, { method: 'DELETE' });
      loadReminders();
    } catch (err) {
      alert('Error cancelling reminder: ' + err.message);
    }
  };

  // System Health
  async function fetchSystemHealth(quiet = false) {
    const systemInfoBox = el('system-info-box');
    const statusDot = el('status-dot');

    try {
      const resp = await apiFetch('/health');
      const health = await resp.json();
      if (systemInfoBox) systemInfoBox.textContent = JSON.stringify(health, null, 2);
      if (statusDot) {
        statusDot.className = health.status === 'ok' ? 'status-indicator online' : 'status-indicator offline';
        statusDot.textContent = health.status === 'ok' ? 'Online' : 'Degraded';
      }
    } catch (err) {
      if (systemInfoBox) {
        systemInfoBox.textContent = err.message.includes('Unauthorized')
          ? 'Authentication required. Enter API Token below.'
          : 'Error connecting to KAI API server.';
      }
      if (statusDot) {
        statusDot.className = 'status-indicator offline';
        statusDot.textContent = err.message.includes('Unauthorized') ? 'Auth Required' : 'Offline';
      }
      if (!quiet && err.message.includes('Unauthorized')) {
        switchView('settings');
      }
    }
  }

  // Web Push Subscription Logic
  async function requestPushPermission() {
    try {
      if (!('Notification' in window)) {
        alert('Notifications are not supported by this browser.');
        return;
      }
      const permission = await Notification.requestPermission();
      if (permission === 'granted') {
        alert('Push notification permission granted!');
      } else {
        alert('Notification permission denied.');
      }
    } catch (e) {
      alert('Push notifications require HTTPS or local connection.');
    }
  }

  // Utilities
  function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;');
  }

  // Safe DOM Load execution
  if (document.readyState === 'interactive' || document.readyState === 'complete') {
    init();
  } else {
    document.addEventListener('DOMContentLoaded', init);
  }
})();
