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
    isStreaming: false,
    voiceMode: localStorage.getItem('kai_voice_mode') === 'true',
    currentAudio: null,
    mediaRecorder: null,
    audioChunks: [],
    audioContext: null,
    analyser: null,
    animFrameId: null
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
    updateVoiceModeUI();
    setupVoiceRecorderUI();

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

    // Gym View Logic
  async function loadGymStats() {
    const prsContainer = el('gym-prs-list');
    const volContainer = el('gym-volume-list');
    if (!prsContainer || !volContainer) return;

    prsContainer.innerHTML = '<div class="empty-state">Loading PRs...</div>';
    volContainer.innerHTML = '<div class="empty-state">Loading volume...</div>';

    try {
      const resp = await apiFetch('/gym/stats');
      const data = await resp.json();
      const stats = data.stats || {};

      // Render PRs
      if (!stats.prs || stats.prs.length === 0) {
        prsContainer.innerHTML = '<div class="empty-state">No PRs recorded yet. Log a workout to start!</div>';
      } else {
        prsContainer.innerHTML = '';
        stats.prs.forEach((pr) => {
          const item = document.createElement('div');
          item.style.padding = '8px 0';
          item.style.borderBottom = '1px solid rgba(255,255,255,0.05)';
          item.innerHTML = `
            <div style="font-weight: 600; text-transform: capitalize; color: var(--accent);">${escapeHtml(pr.exercise)}</div>
            <div style="font-size: 0.85rem; opacity: 0.8;">
              ${pr.best_weight} kg × ${pr.best_reps} reps | <strong>Est 1RM: ${pr.est_1rm} kg</strong>
            </div>
          `;
          prsContainer.appendChild(item);
        });
      }

      // Render Weekly Volume
      if (!stats.weekly_volume) {
        volContainer.innerHTML = '<div class="empty-state">No volume logged this week.</div>';
      } else {
        volContainer.innerHTML = '';
        Object.entries(stats.weekly_volume).forEach(([group, vol]) => {
          if (vol > 0) {
            const item = document.createElement('div');
            item.style.display = 'flex';
            item.style.justifyContent = 'space-between';
            item.style.padding = '6px 0';
            item.style.borderBottom = '1px solid rgba(255,255,255,0.05)';
            item.innerHTML = `<span>${group}</span><strong style="color: var(--accent);">${vol} kg</strong>`;
            volContainer.appendChild(item);
          }
        });
        if (!volContainer.innerHTML) {
          volContainer.innerHTML = '<div class="empty-state">0 kg logged in the past 7 days.</div>';
        }
      }
    } catch (err) {
      if (prsContainer) prsContainer.innerHTML = `<div class="empty-state" style="color: var(--danger)">Error: ${escapeHtml(err.message)}</div>`;
    }
  }

  async function logWorkoutFromUI() {
    const textEl = el('gym-sets-input');
    const splitEl = el('gym-split-input');
    if (!textEl || !textEl.value.trim()) {
      alert('Please enter sets to log (e.g. bench 3x8 at 60).');
      return;
    }

    try {
      const resp = await apiFetch('/gym/workout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          split_name: (splitEl && splitEl.value.trim()) ? splitEl.value.trim() : 'Push/Pull/Legs',
          sets_text: textEl.value.trim()
        })
      });
      const data = await resp.json();
      textEl.value = '';
      let msg = `Logged workout successfully!`;
      if (data.workout && data.workout.pr_notifications && data.workout.pr_notifications.length > 0) {
        msg += `\n🎉 ${data.workout.pr_notifications.length} NEW PR(S) DETECTED!`;
      }
      alert(msg);
      loadGymStats();
    } catch (err) {
      alert('Failed to log workout: ' + err.message);
    }
  }

  async function logBodyWeightFromUI() {
    const weightEl = el('gym-body-weight');
    const fatEl = el('gym-body-fat');
    if (!weightEl || !weightEl.value) {
      alert('Please enter weight in kg.');
      return;
    }

    try {
      await apiFetch('/gym/body', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          weight_kg: parseFloat(weightEl.value),
          body_fat_pct: fatEl.value ? parseFloat(fatEl.value) : null
        })
      });
      alert(`Logged body weight: ${weightEl.value} kg`);
      weightEl.value = '';
      if (fatEl) fatEl.value = '';
      loadGymStats();
    } catch (err) {
      alert('Failed to log weight: ' + err.message);
    }
  }

  // Schedule View Logic
  async function loadSchedule() {
    const timelineList = el('schedule-timeline-list');
    const freeBanner = el('schedule-free-banner');
    if (!timelineList) return;

    timelineList.innerHTML = '<div class="empty-state">Loading schedule...</div>';
    loadFreeWindowsUI();

    try {
      const resp = await apiFetch('/schedule/today');
      const data = await resp.json();
      const blocks = data.blocks || [];

      if (blocks.length === 0) {
        timelineList.innerHTML = '<div class="empty-state">No blocks scheduled for today. Click <strong>⚡ Generate Plan</strong> to create one!</div>';
        return;
      }

      timelineList.innerHTML = '';
      blocks.forEach((b) => {
        const item = document.createElement('div');
        item.style.display = 'flex';
        item.style.alignItems = 'center';
        item.style.justifyContent = 'space-between';
        item.style.padding = '10px 12px';
        item.style.marginBottom = '8px';
        item.style.background = 'rgba(255,255,255,0.03)';
        item.style.borderLeft = b.locked ? '4px solid var(--accent)' : '4px solid var(--warning)';
        item.style.borderRadius = '6px';

        const isDone = b.status === 'completed';
        item.innerHTML = `
          <div style="display: flex; align-items: center; gap: 10px;">
            <input type="checkbox" ${isDone ? 'checked' : ''} onchange="toggleScheduleBlockStatus('${b.id}', '${b.status}')" style="width: 18px; height: 18px; cursor: pointer;" />
            <div>
              <div style="font-weight: 600; ${isDone ? 'text-decoration: line-through; opacity: 0.6;' : ''}">${escapeHtml(b.title)}</div>
              <div style="font-size: 0.8rem; opacity: 0.7;">
                ${b.start} – ${b.end} | <span style="text-transform: capitalize;">${b.type}</span> ${b.locked ? '(Locked)' : ''}
              </div>
            </div>
          </div>
          <span style="font-size: 0.75rem; padding: 2px 8px; border-radius: 12px; background: rgba(255,255,255,0.08);">${b.status}</span>
        `;
        timelineList.appendChild(item);
      });
    } catch (err) {
      if (timelineList) timelineList.innerHTML = `<div class="empty-state" style="color: var(--danger)">Error: ${escapeHtml(err.message)}</div>`;
    }
  }

  async function loadFreeWindowsUI() {
    const freeBanner = el('schedule-free-banner');
    if (!freeBanner) return;
    try {
      const resp = await apiFetch('/schedule/free');
      const data = await resp.json();
      freeBanner.innerHTML = `💡 <strong>Free Time:</strong> ${escapeHtml(data.human_readable)}`;
    } catch (err) {
      freeBanner.innerHTML = 'Unable to calculate free windows.';
    }
  }

  async function generateDailyPlanUI() {
    try {
      const resp = await apiFetch('/schedule/plan', { method: 'POST' });
      const data = await resp.json();
      alert(`Plan generated! Total ${data.plan.total_blocks} blocks scheduled for tomorrow.`);
      loadSchedule();
    } catch (err) {
      alert('Failed to generate plan: ' + err.message);
    }
  }

  async function addScheduleBlockFromUI() {
    const titleEl = el('sched-title-input');
    const startEl = el('sched-start-input');
    const endEl = el('sched-end-input');
    const typeEl = el('sched-type-input');

    if (!titleEl || !titleEl.value.trim()) {
      alert('Please enter a title for the block.');
      return;
    }

    try {
      await apiFetch('/schedule/block', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: titleEl.value.trim(),
          start_time: startEl.value,
          end_time: endEl.value,
          block_type: typeEl.value
        })
      });
      titleEl.value = '';
      loadSchedule();
    } catch (err) {
      alert('Failed to add schedule block: ' + err.message);
    }
  }

  async function triggerMorningBriefUI() {
    try {
      const resp = await apiFetch('/schedule/briefing/morning', { method: 'POST' });
      const data = await resp.json();
      alert(data.message_sent);
    } catch (err) {
      alert('Failed to send morning brief: ' + err.message);
    }
  }

  async function triggerEveningCheckinUI() {
    try {
      const resp = await apiFetch('/schedule/briefing/evening', { method: 'POST' });
      const data = await resp.json();
      alert(data.message_sent);
    } catch (err) {
      alert('Failed to send evening check-in: ' + err.message);
    }
  }

  window.toggleScheduleBlockStatus = async function(blockId, currentStatus) {
    const newStatus = currentStatus === 'completed' ? 'scheduled' : 'completed';
    try {
      await apiFetch(`/schedule/block/${blockId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: newStatus })
      });
      loadSchedule();
    } catch (err) {
      alert('Failed to update status: ' + err.message);
    }
  };

  // Settings & System Functions
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

    // Gym buttons
    const btnLogWorkout = el('btn-log-workout');
    if (btnLogWorkout) btnLogWorkout.addEventListener('click', (e) => { e.preventDefault(); logWorkoutFromUI(); });

    const btnLogBody = el('btn-log-body');
    if (btnLogBody) btnLogBody.addEventListener('click', (e) => { e.preventDefault(); logBodyWeightFromUI(); });

    const btnRefreshGym = el('btn-refresh-gym');
    if (btnRefreshGym) btnRefreshGym.addEventListener('click', (e) => { e.preventDefault(); loadGymStats(); });

    // Schedule buttons
    const btnGenPlan = el('btn-generate-plan');
    if (btnGenPlan) btnGenPlan.addEventListener('click', (e) => { e.preventDefault(); generateDailyPlanUI(); });

    const btnFreeWin = el('btn-free-windows');
    if (btnFreeWin) btnFreeWin.addEventListener('click', (e) => { e.preventDefault(); loadFreeWindowsUI(); });

    const btnBriefMorn = el('btn-brief-morning');
    if (btnBriefMorn) btnBriefMorn.addEventListener('click', (e) => { e.preventDefault(); triggerMorningBriefUI(); });

    const btnBriefEve = el('btn-brief-evening');
    if (btnBriefEve) btnBriefEve.addEventListener('click', (e) => { e.preventDefault(); triggerEveningCheckinUI(); });

    const btnAddSched = el('btn-add-schedule-block');
    if (btnAddSched) btnAddSched.addEventListener('click', (e) => { e.preventDefault(); addScheduleBlockFromUI(); });

    // News buttons
    const btnFetchNews = el('btn-fetch-news');
    if (btnFetchNews) btnFetchNews.addEventListener('click', (e) => { e.preventDefault(); fetchLatestNewsUI(); });

    const srcFilter = el('news-source-filter');
    if (srcFilter) srcFilter.addEventListener('change', () => loadNews());

    const savedFilter = el('news-saved-filter');
    if (savedFilter) savedFilter.addEventListener('change', () => loadNews());

    // Voice mode toggles
    const btnVoiceToggle = el('btn-voice-mode-toggle');
    if (btnVoiceToggle) {
      btnVoiceToggle.addEventListener('click', (e) => {
        e.preventDefault();
        setVoiceMode(!state.voiceMode);
      });
    }

    const chkVoiceSettings = el('voice-mode-checkbox');
    if (chkVoiceSettings) {
      chkVoiceSettings.addEventListener('change', (e) => {
        setVoiceMode(e.target.checked);
      });
    }

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
    if (viewName === 'gym') loadGymStats();
    if (viewName === 'schedule') loadSchedule();
    if (viewName === 'news') loadNews();
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
  async function sendMessage(onComplete = null) {
    const chatInput = el('chat-input');
    const btnSend = el('btn-send');
    if (!chatInput) return;

    const text = chatInput.value.trim();
    if (!text || state.isStreaming) {
      if (onComplete) onComplete();
      return;
    }

    // Barge-in: stop any current response audio playback
    stopCurrentAudioPlayback();

    chatInput.value = '';
    chatInput.style.height = 'auto';

    // Append User Message
    appendMessage('user', text);

    state.isStreaming = true;
    if (btnSend) btnSend.disabled = true;

    // Create Assistant Message container
    const msgCard = appendMessage('assistant', '');
    const contentDiv = msgCard.querySelector('.msg-content');

    let accumulatedAssistantText = '';

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
              if (event.type === 'token') {
                accumulatedAssistantText += event.content || '';
              }
              handleSSEEvent(event, contentDiv);
            } catch (err) {
              console.warn('Malformed SSE data:', dataStr);
            }
          }
        }
      }

      // Voice Mode playback with completion callback
      if ((state.voiceMode || state.continuousVoiceActive) && accumulatedAssistantText.trim()) {
        playResponseAudio(accumulatedAssistantText, onComplete);
      } else {
        if (onComplete) onComplete();
      }
    } catch (err) {
      console.error('Streaming error:', err);
      contentDiv.innerHTML += `<br><span style="color:var(--danger, #ff4d4f)">Error: ${err.message}</span>`;
      if (err.message.includes('Unauthorized')) {
        switchView('settings');
      }
      if (onComplete) onComplete();
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
      <div class="msg-header" style="display: flex; justify-content: space-between; align-items: center;">
        <div>
          <span class="sender-name">${role === 'user' ? 'You' : 'KAI'}</span>
          <span class="msg-time">${timeStr}</span>
        </div>
        ${role === 'assistant' ? `<button class="icon-btn-text" style="font-size: 0.78rem; padding: 2px 6px; background: rgba(255,255,255,0.06); border-radius: 4px; border: 1px solid var(--border, #30363d); cursor: pointer;" onclick="speakMessageContent(this)">🔊 Speak</button>` : ''}
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

  // News View Logic
  async function loadNews() {
    const container = el('news-container');
    if (!container) return;
    container.innerHTML = '<div class="empty-state">Loading news items...</div>';

    const sourceSelect = el('news-source-filter');
    const savedCheck = el('news-saved-filter');

    const source = sourceSelect ? sourceSelect.value : '';
    const saved = savedCheck ? savedCheck.checked : false;

    let queryParams = [];
    if (source) queryParams.push(`source=${encodeURIComponent(source)}`);
    if (saved) queryParams.push(`saved=true`);
    const qStr = queryParams.length ? '?' + queryParams.join('&') : '';

    try {
      const resp = await apiFetch(`/news${qStr}`);
      const data = await resp.json();
      const items = data.items || [];

      if (items.length === 0) {
        container.innerHTML = '<div class="empty-state">No news items found. Click "Fetch Latest" to fetch recent papers & articles!</div>';
        return;
      }

      container.innerHTML = '';
      items.forEach((item) => {
        const card = document.createElement('div');
        card.className = 'item-card';
        card.style.flexDirection = 'column';
        card.style.alignItems = 'flex-start';
        card.style.gap = '8px';

        const sourceLabel = item.source.toUpperCase().replace('_', ' ');
        const scorePct = Math.round((item.relevance_score || 0) * 100);
        const scoreBadgeColor = scorePct >= 80 ? '#52c41a' : scorePct >= 60 ? '#1890ff' : '#faad14';

        card.innerHTML = `
          <div style="display: flex; justify-content: space-between; width: 100%; align-items: center;">
            <div style="display: flex; gap: 8px; align-items: center;">
              <span style="font-size: 0.72rem; font-weight: 700; padding: 2px 8px; border-radius: 4px; background: rgba(255,255,255,0.1); color: var(--accent);">${sourceLabel}</span>
              <span style="font-size: 0.72rem; font-weight: 600; padding: 2px 8px; border-radius: 4px; background: rgba(255,255,255,0.05); color: ${scoreBadgeColor};">Score: ${scorePct}%</span>
            </div>
            <span style="font-size: 0.75rem; color: var(--text-muted);">${item.published_at}</span>
          </div>
          <div style="font-size: 1rem; font-weight: 600; margin-top: 4px;">
            <a href="${escapeHtml(item.url)}" target="_blank" style="color: var(--text-primary); text-decoration: none; border-bottom: 1px dotted var(--accent);">${escapeHtml(item.title)}</a>
          </div>
          <div style="font-size: 0.85rem; color: var(--text-muted); line-height: 1.4;">${escapeHtml(item.summary)}</div>
          <div style="display: flex; gap: 8px; margin-top: 6px; width: 100%; justify-content: flex-end;">
            <button class="btn-secondary" style="font-size: 0.78rem;" onclick="explainArticleUI('${item.id}')">💡 Explain Paper</button>
            <button class="btn-secondary" style="font-size: 0.78rem; background: ${item.saved ? 'rgba(255, 193, 7, 0.2)' : 'transparent'}; color: ${item.saved ? '#ffc107' : 'inherit'};" onclick="toggleSaveArticleUI('${item.id}', ${item.saved})">
              ${item.saved ? '⭐ Saved' : '☆ Save for Later'}
            </button>
          </div>
        `;
        container.appendChild(card);
      });
    } catch (err) {
      container.innerHTML = `<div class="empty-state" style="color: var(--danger)">Error: ${escapeHtml(err.message)}</div>`;
    }
  }

  async function fetchLatestNewsUI() {
    const container = el('news-container');
    if (container) container.innerHTML = '<div class="empty-state">Fetching arXiv papers, Hacker News, & HuggingFace trending papers... Please wait.</div>';
    try {
      const resp = await apiFetch('/news/fetch', { method: 'POST' });
      const res = await resp.json();
      alert(`Fetched! ${res.new_items_added} new items added. (${res.breaking_alerts_sent} breaking alerts sent)`);
      loadNews();
    } catch (err) {
      alert('Failed to fetch news: ' + err.message);
      loadNews();
    }
  }

  window.toggleSaveArticleUI = async function(itemId, currentSaved) {
    try {
      await apiFetch(`/news/${itemId}/save`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ saved: !currentSaved })
      });
      loadNews();
    } catch (err) {
      alert('Failed to save article: ' + err.message);
    }
  };

  window.explainArticleUI = async function(itemId) {
    try {
      alert('Generating detailed explanation with KAI... Please wait a few seconds.');
      const resp = await apiFetch(`/news/${itemId}/explain`, { method: 'POST' });
      const data = await resp.json();
      if (data.explanation) {
        alert(`💡 Paper Explanation for "${data.title}":\n\n${data.explanation}`);
      } else {
        alert('Could not generate explanation.');
      }
    } catch (err) {
      alert('Error explaining paper: ' + err.message);
    }
  };

  // Voice Subsystem & Audio Functions
  function stopCurrentAudioPlayback() {
    if (state.currentAudio) {
      try {
        state.currentAudio.pause();
        state.currentAudio.currentTime = 0;
      } catch (e) {}
      state.currentAudio = null;
    }
    if (window.speechSynthesis && window.speechSynthesis.speaking) {
      window.speechSynthesis.cancel();
    }
  }

  function updateVoiceModeUI() {
    const btnToggle = el('btn-voice-mode-toggle');
    const chkSettings = el('voice-mode-checkbox');

    if (btnToggle) {
      btnToggle.style.background = state.voiceMode ? 'rgba(24, 144, 255, 0.25)' : 'rgba(255,255,255,0.08)';
      btnToggle.style.color = state.voiceMode ? '#1890ff' : 'inherit';
      btnToggle.title = state.voiceMode ? 'Voice Mode ON (Click to Mute)' : 'Voice Mode OFF (Click to Enable Auto-play)';
      btnToggle.textContent = state.voiceMode ? '🔊' : '🔇';
    }
    if (chkSettings) {
      chkSettings.checked = state.voiceMode;
    }
  }

  function setVoiceMode(enabled) {
    state.voiceMode = enabled;
    localStorage.setItem('kai_voice_mode', enabled ? 'true' : 'false');
    updateVoiceModeUI();
    if (!enabled) stopCurrentAudioPlayback();
  }

  async function playResponseAudio(text, onComplete = null) {
    if (!text || !text.trim()) {
      if (onComplete) onComplete();
      return;
    }
    stopCurrentAudioPlayback();

    const cleanText = text.replace(/[\*\_`#~]/g, '').replace(/\[([^\]]+)\]\([^)]+\)/g, '$1').trim();
    if (!cleanText) {
      if (onComplete) onComplete();
      return;
    }

    let finished = false;
    const handleEnd = () => {
      if (!finished) {
        finished = true;
        if (onComplete) onComplete();
      }
    };

    try {
      const resp = await apiFetch(`/voice/tts?text=${encodeURIComponent(cleanText.slice(0, 350))}`);
      if (resp.ok) {
        const blob = await resp.blob();
        const audioUrl = URL.createObjectURL(blob);
        const audio = new Audio(audioUrl);
        state.currentAudio = audio;
        audio.onended = handleEnd;
        audio.onerror = () => fallbackWebSpeech(cleanText, handleEnd);
        audio.play().catch((err) => {
          console.warn('Auto-play audio blocked, fallback to SpeechSynthesis:', err);
          fallbackWebSpeech(cleanText, handleEnd);
        });
        return;
      }
    } catch (err) {
      console.warn('TTS fetch failed, fallback to SpeechSynthesis:', err);
    }

    fallbackWebSpeech(cleanText, handleEnd);
  }

  function fallbackWebSpeech(text, onComplete = null) {
    let finished = false;
    const handleEnd = () => {
      if (!finished) {
        finished = true;
        if (onComplete) onComplete();
      }
    };

    if ('speechSynthesis' in window) {
      stopCurrentAudioPlayback();
      const utterance = new SpeechSynthesisUtterance(text.slice(0, 300));
      utterance.rate = 1.0;
      utterance.pitch = 1.0;
      utterance.onend = handleEnd;
      utterance.onerror = handleEnd;
      window.speechSynthesis.speak(utterance);
    } else {
      handleEnd();
    }
  }

  window.speakMessageContent = function(btn) {
    const card = btn.closest('.message');
    if (!card) return;
    const contentDiv = card.querySelector('.msg-content');
    if (contentDiv) {
      const text = contentDiv.innerText || contentDiv.textContent;
      playResponseAudio(text);
    }
  };

  // Full-Duplex Continuous Conversational Voice Loop
  function setupVoiceRecorderUI() {
    const btnMic = el('btn-mic');
    if (!btnMic) return;

    btnMic.addEventListener('click', (e) => {
      e.preventDefault();
      toggleContinuousVoiceMode();
    });
  }

  function toggleContinuousVoiceMode() {
    const btnMic = el('btn-mic');
    state.continuousVoiceActive = !state.continuousVoiceActive;

    if (state.continuousVoiceActive) {
      if (btnMic) btnMic.classList.add('active');
      startContinuousVoiceLoop();
    } else {
      stopContinuousVoiceMode();
    }
  }

  function stopContinuousVoiceMode() {
    state.continuousVoiceActive = false;
    stopCurrentAudioPlayback();
    if (state.recognition) {
      try { state.recognition.abort(); } catch (e) {}
      state.recognition = null;
    }
    stopAudioRecording();

    const btnMic = el('btn-mic');
    if (btnMic) {
      btnMic.classList.remove('active');
      // Reset inline styles that might have been applied before
      btnMic.style.background = '';
      btnMic.style.borderColor = '';
      btnMic.style.color = '';
      btnMic.title = 'Start Live Voice Mode';
    }

    const waveformContainer = el('voice-waveform-container');
    // Only hide if we aren't showing an error
    const waveformStatus = el('voice-waveform-status');
    if (waveformStatus && waveformStatus.textContent.includes('error')) {
      setTimeout(() => { if (waveformContainer) waveformContainer.style.display = 'none'; }, 3000);
    } else {
      if (waveformContainer) waveformContainer.style.display = 'none';
    }
  }

  async function startContinuousVoiceLoop() {
    if (!state.continuousVoiceActive) return;

    if (!window.isSecureContext && location.hostname !== 'localhost' && location.hostname !== '127.0.0.1') {
      alert("Microphone is blocked by Android Chrome on insecure HTTP connections.\n\nTo use Voice Mode over Tailscale:\n1. Open Chrome and go to chrome://flags/#unsafely-treat-insecure-origin-as-secure\n2. Add this IP address to the list.\n3. Relaunch Chrome.\n\nVoice Mode cannot start without this flag.");
      stopContinuousVoiceMode();
      return;
    }

    stopCurrentAudioPlayback();

    const waveformContainer = el('voice-waveform-container');
    const waveformStatus = el('voice-waveform-status');
    const canvas = el('voice-waveform-canvas');

    if (waveformContainer) waveformContainer.style.display = 'flex';
    if (waveformStatus) waveformStatus.textContent = 'Listening... Speak to KAI';

    runMediaRecorderLoop(waveformContainer, waveformStatus, canvas);
  }

  function getUserMediaStream(constraints) {
    if (navigator.mediaDevices && typeof navigator.mediaDevices.getUserMedia === 'function') {
      return navigator.mediaDevices.getUserMedia(constraints);
    }
    const legacyFn = navigator.getUserMedia ||
                     navigator.webkitGetUserMedia ||
                     navigator.mozGetUserMedia ||
                     navigator.msGetUserMedia;
    if (typeof legacyFn === 'function') {
      return new Promise((resolve, reject) => {
        legacyFn.call(navigator, constraints, resolve, reject);
      });
    }
    return Promise.reject(new Error('Microphone stream unavailable'));
  }

  async function runMediaRecorderLoop(waveformContainer, waveformStatus, canvas) {
    state.audioChunks = [];

    try {
      const stream = await getUserMediaStream({ audio: true });

      const AudioContext = window.AudioContext || window.webkitAudioContext;
      if (AudioContext) {
        state.audioContext = new AudioContext();
        state.analyser = state.audioContext.createAnalyser();
        const source = state.audioContext.createMediaStreamSource(stream);
        source.connect(state.analyser);
        state.analyser.fftSize = 256;
        drawWaveformCanvas(canvas);
      }

      state.mediaRecorder = new MediaRecorder(stream);
      state.mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) state.audioChunks.push(event.data);
      };

      state.mediaRecorder.onstop = async () => {
        if (state.animFrameId) cancelAnimationFrame(state.animFrameId);
        if (state.audioContext) state.audioContext.close();
        stream.getTracks().forEach((t) => t.stop());

        if (waveformStatus) waveformStatus.textContent = 'Transcribing with Whisper...';

        const audioBlob = new Blob(state.audioChunks, { type: 'audio/webm' });
        
        const onTranscriptionAndSpeechDone = () => {
          if (state.continuousVoiceActive) {
            setTimeout(() => startContinuousVoiceLoop(), 400);
          } else {
            if (waveformContainer) waveformContainer.style.display = 'none';
          }
        };

        if (state.audioChunks.length > 0) {
           await sendAudioToSTT(audioBlob, onTranscriptionAndSpeechDone);
        } else {
           onTranscriptionAndSpeechDone();
        }
      };

      state.mediaRecorder.start(250); // Timeslice 250ms ensures chunks are populated reliably on mobile
    } catch (err) {
      console.warn('Microphone stream error:', err);
      if (waveformStatus) waveformStatus.textContent = 'Mic error: ' + (err.message || 'Blocked');
      stopContinuousVoiceMode();
    }
  }

  function stopAudioRecording() {
    if (state.mediaRecorder && state.mediaRecorder.state !== 'inactive') {
      state.mediaRecorder.stop();
    }
  }

  function drawWaveformCanvas(canvas) {
    if (!canvas || !state.analyser) return;
    const ctx = canvas.getContext('2d');
    const bufferLength = state.analyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);

    const MAX_SILENCE_MS = 2500; // 2.5 seconds pause triggers instant processing
    const MAX_WAIT_MS = 12000; // Absolute max wait if user clicks but never speaks
    
    // Dynamic Noise Gate Params
    let noiseFloor = 255;
    const VOICE_BIN_START = 2; // ~375Hz 
    const VOICE_BIN_END = 18;  // ~3400Hz (core human vocal range)
    const VAD_SENSITIVITY_MARGIN = 15; // Requires 15 units above ambient noise to trigger
    
    let lastSpokeTime = Date.now();
    let startTime = Date.now();
    let hasSpoken = false;

    function renderFrame() {
      state.animFrameId = requestAnimationFrame(renderFrame);
      state.analyser.getByteFrequencyData(dataArray);

      ctx.clearRect(0, 0, canvas.width, canvas.height);

      const barWidth = (canvas.width / bufferLength) * 1.5;
      let x = 0;

      let voiceEnergySum = 0;
      let voiceBinsCount = 0;

      for (let i = 0; i < bufferLength; i++) {
        const value = dataArray[i];
        
        // Sum energy exclusively in human vocal frequency bands
        if (i >= VOICE_BIN_START && i <= VOICE_BIN_END) {
          voiceEnergySum += value;
          voiceBinsCount++;
        }

        const barHeight = (value / 255) * canvas.height;
        ctx.fillStyle = `rgb(24, ${Math.min(255, 144 + value)}, 255)`;
        ctx.fillRect(x, canvas.height - barHeight, barWidth - 1, barHeight);
        x += barWidth;
      }

      // Smart Voice Activity Detection (VAD) via Dynamic Noise Floor
      const currentVoiceEnergy = voiceEnergySum / (voiceBinsCount || 1);
      let isSpeakingNow = false;

      // Adapt to ultra-quiet moments instantly
      if (currentVoiceEnergy < noiseFloor) {
        noiseFloor = currentVoiceEnergy;
      } 
      // Trigger speaking if energy spikes clearly above the steady noise floor
      else if (currentVoiceEnergy > noiseFloor + VAD_SENSITIVITY_MARGIN) {
        isSpeakingNow = true;
      } 
      // If we are NOT speaking, slowly adapt to rising ambient noise (like a fan turning on)
      else {
        noiseFloor += 0.2; 
      }
      
      if (isSpeakingNow) {
        hasSpoken = true;
        lastSpokeTime = Date.now();
      } else {
        if (hasSpoken && (Date.now() - lastSpokeTime > MAX_SILENCE_MS)) {
          if (state.mediaRecorder && state.mediaRecorder.state === 'recording') {
            console.log(`[VAD] ${MAX_SILENCE_MS}ms silence detected. Dynamic floor: ${noiseFloor.toFixed(1)}. Processing voice.`);
            state.mediaRecorder.stop();
            hasSpoken = false;
          }
        } else if (!hasSpoken && (Date.now() - startTime > MAX_WAIT_MS)) {
           if (state.mediaRecorder && state.mediaRecorder.state === 'recording') {
            console.log('[VAD] No speech detected for 12 seconds. Aborting listen loop to prevent hang.');
            state.mediaRecorder.stop();
          }
        }
      }
    }
    renderFrame();
  }

  async function convertWebmToWav(blob) {
    if (!blob || blob.size === 0) {
      throw new Error('Empty audio stream received.');
    }
    const arrayBuffer = await blob.arrayBuffer();
    const audioContext = new (window.AudioContext || window.webkitAudioContext)();
    const audioBuffer = await audioContext.decodeAudioData(arrayBuffer);
    
    const offlineCtx = new (window.OfflineAudioContext || window.webkitOfflineAudioContext)(1, audioBuffer.duration * 16000, 16000);
    const source = offlineCtx.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(offlineCtx.destination);
    source.start();
    const resampledBuffer = await offlineCtx.startRendering();

    const channelData = resampledBuffer.getChannelData(0);
    const wavBuffer = new ArrayBuffer(44 + channelData.length * 2);
    const view = new DataView(wavBuffer);
    
    const writeString = (view, offset, string) => {
      for (let i = 0; i < string.length; i++) {
        view.setUint8(offset + i, string.charCodeAt(i));
      }
    };
    
    writeString(view, 0, 'RIFF');
    view.setUint32(4, 36 + channelData.length * 2, true);
    writeString(view, 8, 'WAVE');
    writeString(view, 12, 'fmt ');
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true); 
    view.setUint16(22, 1, true); 
    view.setUint32(24, 16000, true); 
    view.setUint32(28, 16000 * 2, true); 
    view.setUint16(32, 2, true); 
    view.setUint16(34, 16, true); 
    writeString(view, 36, 'data');
    view.setUint32(40, channelData.length * 2, true);
    
    let offset = 44;
    for (let i = 0; i < channelData.length; i++) {
        let s = Math.max(-1, Math.min(1, channelData[i]));
        view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
        offset += 2;
    }
    
    return new Blob([wavBuffer], { type: 'audio/wav' });
  }

  async function sendAudioToSTT(audioBlob, onComplete) {
    const chatInput = el('chat-input');
    try {
      if (audioBlob.size < 100) {
        console.warn('Audio blob too small, parsing as silent abort. Ignoring.');
        if (onComplete) onComplete();
        return;
      }
      
      const wavBlob = await convertWebmToWav(audioBlob);
      const formData = new FormData();
      formData.append('file', wavBlob, 'speech.wav');

      const resp = await apiFetch('/voice/stt', {
        method: 'POST',
        body: formData
      });

      const res = await resp.json();
      if (res.text && res.text.trim() && res.text !== '[Voice recording received]') {
        const transcribedText = res.text.trim();
        if (chatInput) {
          chatInput.value = transcribedText;
        }
        sendMessage(onComplete);
      } else {
        if (onComplete) onComplete();
      }
    } catch (err) {
      console.error('STT Transcription error:', err);
      if (chatInput) chatInput.placeholder = 'STT error: ' + err.message;
      if (onComplete) onComplete();
    }
  }

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
