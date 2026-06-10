(function () {
  const MCH = "/api/mcharness";
  const JULES_VIEW_URL = "https://jules.google.com/session";
  // Minimal state for Agent Library + Codex flow + Live Monitor
  const state = {
    repos: [],
    lanes: [],
    agents: [],
    agentTemplates: [],
    registryWriteEnabled: false,
    addAgent: {
      step: "choose",
      mode: "create",
      editingAgentId: "",
      templateAdapter: "",
      saving: false,
      testing: false,
      lastTestStatus: "",
      error: "",
    },
    health: {},
    selectedThreadId: "",
    selectedQueueItemId: "",
    promptSubmittedAt: 0,
    liveMonitorExpanded: false,
    liveAutoScroll: true,
    lastMonitorTranscriptText: "",
    activeSection: "mission",
    recentRuns: [],
    recentEvidence: [],
    activeWardenRunId: "",
    activeCaptainPlan: null,
    missionWorklog: [],
    missionTimelineFilter: "all",
    captainDeck: {
      configured: false,
      planningEnabled: false,
      privateKeySetupEnabled: false,
      keySource: "missing",
      model: "openrouter/auto",
      notes: [],
      repoId: "",
      repoPath: "",
      laneId: "codex_cli",
      goal: "",
      plan: null,
      loading: false,
      error: "",
      keyFormVisible: false,
      keySaving: false,
      keyError: "",
      keyModel: "openrouter/auto",
    },
  };

  // Helper for API calls (minimal)
  async function requestJson(url, opts = {}) {
    const res = await fetch(url, {
      headers: { "content-type": "application/json" },
      ...opts,
      body: opts.body ? (typeof opts.body === "string" ? opts.body : JSON.stringify(opts.body)) : undefined,
    });
    if (!res.ok) {
      const txt = await res.text().catch(() => "");
      throw new Error(txt || res.statusText);
    }
    return res.json();
  }

  function setQuickReplyStatus(message, isError = false) {
    const el = document.getElementById("quick-reply-status");
    if (!el) return;
    el.textContent = message || "";
    el.style.color = isError ? "var(--bad, #ff7e91)" : "var(--muted, #9cacbf)";
  }

  function scrollModalTranscriptToBottom() {
    const pre = document.getElementById("modal-transcript");
    if (!pre) return;
    state.liveScrollProgrammatic = true;
    requestAnimationFrame(() => {
      pre.scrollTop = pre.scrollHeight;
      requestAnimationFrame(() => {
        state.liveScrollProgrammatic = false;
      });
    });
  }

  function isModalTranscriptNearBottom(pre) {
    if (!pre) return true;
    return (pre.scrollHeight - pre.scrollTop - pre.clientHeight) < 80;
  }

  function updateLiveMonitorChrome() {
    const modal = document.getElementById("live-cli-modal");
    const expandBtn = document.getElementById("modal-expand");
    const scrollIndicator = document.getElementById("modal-autoscroll-indicator");
    if (modal) {
      modal.classList.toggle("monitor-expanded", !!state.liveMonitorExpanded);
    }
    if (expandBtn) {
      expandBtn.textContent = state.liveMonitorExpanded ? "Normal View" : "Bigger View";
    }
    if (scrollIndicator) {
      scrollIndicator.textContent = state.liveAutoScroll ? "" : "Scrolled up — updates paused here";
      scrollIndicator.style.display = state.liveAutoScroll ? "none" : "block";
    }
  }

  function pauseLiveAutoScroll() {
    if (!state.liveAutoScroll) return;
    state.liveAutoScroll = false;
    updateLiveMonitorChrome();
  }

  function resumeLiveAutoScroll() {
    state.liveAutoScroll = true;
    updateLiveMonitorChrome();
    scrollModalTranscriptToBottom();
  }

  function escapeHtml(v) {
    return String(v || "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  async function loadCaptainDeckStatus() {
    try {
      const status = await requestJson(`${MCH}/captain/status`);
      const deck = state.captainDeck;
      deck.configured = !!status.configured;
      deck.planningEnabled = !!status.planning_enabled;
      deck.privateKeySetupEnabled = !!status.private_key_setup_enabled;
      deck.keySource = status.key_source || "missing";
      deck.model = status.model || "openrouter/auto";
      if (!deck.keyFormVisible) {
        deck.keyModel = deck.model || "openrouter/auto";
      }
      deck.notes = Array.isArray(status.notes) ? status.notes : [];
      renderCaptainDeck();
      renderSettingsPanel();
      return status;
    } catch (e) {
      const deck = state.captainDeck;
      deck.configured = false;
      deck.planningEnabled = false;
      deck.privateKeySetupEnabled = false;
      deck.keySource = "missing";
      deck.notes = ["Captain status unavailable."];
      renderCaptainDeck();
      renderSettingsPanel();
      return null;
    }
  }

  async function populateCaptainDeckRepos() {
    const sel = document.getElementById("captain-repo-select");
    if (!sel) return;
    sel.innerHTML = '<option value="">Loading repos...</option>';
    try {
      const data = await requestJson(`${MCH}/repos`);
      const repos = data.repos || [];
      state.repos = repos;
      sel.innerHTML = "";
      const fallback = repos.length ? repos : [
        { repo_id: "hybrid-agent-os", label: "hybrid-agent-os", path: "/root/hybrid-agent-os" },
        { repo_id: "mcharness-public-export", label: "mcharness-public-export", path: "/root/mcharness-public-export" },
      ];
      fallback.forEach((repo) => {
        const opt = document.createElement("option");
        opt.value = repo.repo_id || repo.path;
        opt.dataset.repoPath = repo.path || "";
        opt.textContent = repo.label || repo.repo_id || repo.path;
        sel.appendChild(opt);
      });
      if (fallback.length) {
        const current = state.captainDeck.repoId || fallback[0].repo_id || fallback[0].path;
        sel.value = current;
        const selected = sel.selectedOptions[0];
        state.captainDeck.repoId = selected ? selected.value : current;
        state.captainDeck.repoPath = (selected && selected.dataset.repoPath) || fallback[0].path || "";
      }
    } catch (e) {
      sel.innerHTML = '<option value="/root/mcharness-public-export">mcharness-public-export (fallback)</option>';
      sel.value = "/root/mcharness-public-export";
      state.captainDeck.repoId = "mcharness-public-export";
      state.captainDeck.repoPath = "/root/mcharness-public-export";
    }
  }

  function renderCaptainDeck() {
    const deck = state.captainDeck;
    const noteEl = document.getElementById("captain-config-note");
    const settingsStatusEl = document.getElementById("captain-settings-status");
    const settingsNoteEl = document.getElementById("captain-settings-note");
    const keyFormEl = document.getElementById("captain-key-form");
    const setKeyBtn = document.getElementById("captain-set-key");
    const removeKeyBtn = document.getElementById("captain-remove-key");
    const saveKeyBtn = document.getElementById("captain-save-key");
    const cancelKeyBtn = document.getElementById("captain-cancel-key");
    const keyInput = document.getElementById("captain-openrouter-key");
    const modelInput = document.getElementById("captain-openrouter-model");
    const keyFormNoteEl = document.getElementById("captain-key-form-note");
    const statusEl = document.getElementById("captain-plan-status");
    const createBtn = document.getElementById("captain-create-plan");
    const deployBtn = document.getElementById("captain-deploy-first");
    const copyBtn = document.getElementById("captain-copy-plan");
    const planBody = document.getElementById("captain-plan-body");
    const goalEl = document.getElementById("captain-goal");
    const repoSel = document.getElementById("captain-repo-select");
    const laneSel = document.getElementById("captain-agent-select");

    if (goalEl && goalEl.value !== deck.goal) goalEl.value = deck.goal || "";
    if (repoSel && deck.repoId && repoSel.value !== deck.repoId) repoSel.value = deck.repoId;
    if (laneSel && deck.laneId && laneSel.value !== deck.laneId) laneSel.value = deck.laneId;

    if (noteEl) {
      noteEl.textContent = deck.configured
        ? `Captain is configured. Model: ${deck.model}`
        : "Captain is not configured. Set OPENROUTER_API_KEY on the private service.";
      noteEl.style.display = "block";
    }
    if (settingsStatusEl) {
      settingsStatusEl.textContent = `Status: ${deck.configured ? "Configured" : "Not configured"} • Key source: ${deck.keySource || "missing"} • Model: ${deck.model || "openrouter/auto"}`;
    }
    if (settingsNoteEl) {
      if (!deck.privateKeySetupEnabled) {
        settingsNoteEl.textContent = "Captain key setup is available only on the private service.";
      } else if (deck.keySource === "env") {
        settingsNoteEl.textContent = "Captain is configured via environment on this service. Saved keys cannot override it.";
      } else if (deck.keySource === "saved") {
        settingsNoteEl.textContent = "Captain is configured via a saved private key on this service.";
      } else {
        settingsNoteEl.textContent = "Set an OpenRouter key to enable Captain planning on the private service.";
      }
    }
    if (keyFormEl) {
      keyFormEl.style.display = deck.keyFormVisible ? "block" : "none";
    }
    if (setKeyBtn) {
      setKeyBtn.style.display = deck.privateKeySetupEnabled ? "inline-flex" : "inline-flex";
      setKeyBtn.disabled = !deck.privateKeySetupEnabled || deck.keySource === "env" || deck.keySaving;
      setKeyBtn.textContent = deck.keySource === "env" ? "OpenRouter Key in Environment" : "Set OpenRouter Key";
    }
    if (removeKeyBtn) {
      removeKeyBtn.style.display = deck.privateKeySetupEnabled && deck.keySource === "saved" ? "inline-flex" : "none";
      removeKeyBtn.disabled = !deck.privateKeySetupEnabled || deck.keySaving;
    }
    if (saveKeyBtn) {
      saveKeyBtn.disabled = !deck.privateKeySetupEnabled || deck.keySource === "env" || deck.keySaving;
      saveKeyBtn.textContent = deck.keySaving ? "Saving..." : "Save Key";
    }
    if (cancelKeyBtn) {
      cancelKeyBtn.disabled = !!deck.keySaving;
    }
    if (keyInput && keyInput.value && !deck.keyFormVisible) {
      keyInput.value = "";
    }
    if (modelInput) {
      modelInput.value = deck.keyModel || deck.model || "openrouter/auto";
      modelInput.disabled = !deck.privateKeySetupEnabled || deck.keySource === "env" || deck.keySaving;
    }
    if (keyFormNoteEl) {
      if (deck.keyError) {
        keyFormNoteEl.textContent = deck.keyError;
        keyFormNoteEl.style.color = "var(--bad, #ff7e91)";
      } else if (deck.keySaving) {
        keyFormNoteEl.textContent = "Saving OpenRouter key on the private service...";
        keyFormNoteEl.style.color = "var(--muted, #9cacbf)";
      } else if (deck.keySource === "env") {
        keyFormNoteEl.textContent = "Environment key is already active on this service. Saved keys are disabled here.";
        keyFormNoteEl.style.color = "var(--warn, #f0c66a)";
      } else if (!deck.privateKeySetupEnabled) {
        keyFormNoteEl.textContent = "Captain key setup is available only on the private service.";
        keyFormNoteEl.style.color = "var(--warn, #f0c66a)";
      } else {
        keyFormNoteEl.textContent = "The key is stored server-side only for the private service.";
        keyFormNoteEl.style.color = "var(--muted, #9cacbf)";
      }
    }

    if (createBtn) {
      const selectedAgent = (state.agents || []).find((agent) => agent.id === deck.laneId) || {};
      const agentRunnable = selectedAgent.runnable !== false && selectedAgent.adapter === "codex_cli";
      createBtn.disabled = !!deck.loading || !deck.configured || !agentRunnable;
      createBtn.textContent = deck.loading ? "Captain is building the plan..." : "Create Plan";
    }
    if (deployBtn) {
      const selectedAgent = (state.agents || []).find((agent) => agent.id === deck.laneId) || {};
      const agentRunnable = selectedAgent.runnable !== false && selectedAgent.adapter === "codex_cli";
      deployBtn.disabled = !deck.plan || !agentRunnable;
    }
    const captainAgentNote = document.getElementById("captain-agent-note");
    if (captainAgentNote) {
      const selectedAgent = (state.agents || []).find((agent) => agent.id === deck.laneId) || {};
      if (selectedAgent.adapter === "jules_remote") {
        captainAgentNote.textContent = "Jules Remote is configured for planning/status only. Execution comes next.";
        captainAgentNote.style.display = "block";
      } else if (selectedAgent.id && !selectedAgent.runnable) {
        captainAgentNote.textContent = "This agent is registered but not runnable yet.";
        captainAgentNote.style.display = "block";
      } else {
        captainAgentNote.textContent = "";
        captainAgentNote.style.display = "none";
      }
    }
    if (copyBtn) {
      copyBtn.disabled = !deck.plan;
    }
    if (statusEl) {
      if (deck.error) {
        statusEl.textContent = deck.error;
        statusEl.style.color = "var(--bad, #ff7e91)";
      } else if (deck.loading) {
        statusEl.textContent = "Captain is building the plan...";
        statusEl.style.color = "var(--muted, #9cacbf)";
      } else if (deck.plan) {
        statusEl.textContent = `Plan ready: ${deck.plan.title}`;
        statusEl.style.color = "var(--good, #63db9d)";
      } else if (!deck.configured) {
        statusEl.textContent = "Captain is not configured. Set OPENROUTER_API_KEY on the private service.";
        statusEl.style.color = "var(--warn, #f0c66a)";
      } else {
        statusEl.textContent = "";
      }
    }
    if (planBody) {
      if (!deck.plan) {
        planBody.innerHTML = '<div class="muted" style="font-size:0.82em;">Create a plan to see the Captain steps here.</div>';
      } else {
        const steps = deck.plan.steps || [];
        const stepsHtml = steps.map((step) => `
          <details class="captain-step">
            <summary><strong>${escapeHtml(step.title || step.id)}</strong><span class="muted" style="margin-left:8px;">${escapeHtml(step.agent || "codex_cli")}</span></summary>
            <div class="muted" style="font-size:0.76em; margin:4px 0 6px;">Status: ${escapeHtml(step.status || "queued")}</div>
            <pre class="captain-step-prompt">${escapeHtml(step.prompt || "")}</pre>
          </details>
        `).join("");
        planBody.innerHTML = `
          <div class="captain-plan-title"><strong>${escapeHtml(deck.plan.title || "Captain Plan")}</strong></div>
          <div class="captain-plan-summary muted">${escapeHtml(deck.plan.summary || "")}</div>
          <div class="captain-plan-steps">${stepsHtml}</div>
        `;
      }
    }
  }

  async function openCaptainDeckModal() {
    const modal = document.getElementById("captain-deck-modal");
    if (!modal) return;
    modal.style.display = "flex";
    state.captainDeck.error = "";
    state.captainDeck.keyError = "";
    state.captainDeck.keyFormVisible = false;
    renderCaptainDeck();
    await Promise.all([populateCaptainDeckRepos(), loadCaptainDeckStatus(), loadAgents()]);
    populateCaptainAgents();
    renderCaptainDeck();
  }

  function closeCaptainDeckModal() {
    const modal = document.getElementById("captain-deck-modal");
    if (modal) modal.style.display = "none";
  }

  function openCaptainKeyForm() {
    const deck = state.captainDeck;
    if (!deck.privateKeySetupEnabled || deck.keySource === "env") return;
    deck.keyError = "";
    deck.keyFormVisible = true;
    deck.keyModel = deck.keyModel || deck.model || "openrouter/auto";
    renderCaptainDeck();
    const keyInput = document.getElementById("captain-openrouter-key");
    if (keyInput) {
      keyInput.value = "";
      keyInput.focus();
    }
  }

  function closeCaptainKeyForm() {
    const deck = state.captainDeck;
    deck.keyError = "";
    deck.keyFormVisible = false;
    renderCaptainDeck();
  }

  async function saveCaptainKey() {
    const deck = state.captainDeck;
    const keyInput = document.getElementById("captain-openrouter-key");
    const modelInput = document.getElementById("captain-openrouter-model");
    if (!deck.privateKeySetupEnabled || deck.keySource === "env") {
      deck.keyError = "Captain key setup is available only on the private service.";
      renderCaptainDeck();
      return;
    }
    const apiKey = (keyInput && keyInput.value ? keyInput.value : "").trim();
    const model = (modelInput && modelInput.value ? modelInput.value : "").trim() || "openrouter/auto";
    if (!apiKey) {
      deck.keyError = "Enter an OpenRouter API key first.";
      renderCaptainDeck();
      return;
    }
    deck.keySaving = true;
    deck.keyError = "";
    renderCaptainDeck();
    try {
      await requestJson(`${MCH}/captain/key`, {
        method: "POST",
        body: {
          api_key: apiKey,
          model,
        },
      });
      if (keyInput) keyInput.value = "";
      deck.keyFormVisible = false;
      await loadCaptainDeckStatus();
      deck.keyError = "";
      renderCaptainDeck();
    } catch (e) {
      deck.keyError = e.message || String(e);
      renderCaptainDeck();
    } finally {
      deck.keySaving = false;
      renderCaptainDeck();
    }
  }

  async function removeCaptainKey() {
    const deck = state.captainDeck;
    if (!deck.privateKeySetupEnabled || deck.keySource !== "saved") return;
    deck.keySaving = true;
    deck.keyError = "";
    renderCaptainDeck();
    try {
      await requestJson(`${MCH}/captain/key`, {
        method: "DELETE",
      });
      deck.keyFormVisible = false;
      await loadCaptainDeckStatus();
      renderCaptainDeck();
    } catch (e) {
      deck.keyError = e.message || String(e);
      renderCaptainDeck();
    } finally {
      deck.keySaving = false;
      renderCaptainDeck();
    }
  }

  async function createCaptainPlan() {
    const deck = state.captainDeck;
    const goalEl = document.getElementById("captain-goal");
    const repoSel = document.getElementById("captain-repo-select");
    const laneSel = document.getElementById("captain-agent-select");
    if (!goalEl || !repoSel || !laneSel) return;
    const goal = (goalEl.value || "").trim();
    const repoId = repoSel.value;
    const repoPath = (repoSel.selectedOptions[0] && repoSel.selectedOptions[0].dataset.repoPath) || "";
    const laneId = laneSel.value || "codex_cli";
    if (!goal) {
      deck.error = "Describe the goal first.";
      renderCaptainDeck();
      return;
    }
    deck.loading = true;
    deck.error = "";
    deck.goal = goal;
    deck.repoId = repoId;
    deck.repoPath = repoPath;
    deck.laneId = laneId;
    renderCaptainDeck();
    try {
      const plan = await requestJson(`${MCH}/captain/plan`, {
        method: "POST",
        body: {
          goal,
          repo_id: repoId,
          lane_id: laneId,
        },
      });
      deck.plan = plan;
      setActiveCaptainPlan(plan);
      deck.error = "";
      deck.loading = false;
      renderCaptainDeck();
    } catch (e) {
      deck.loading = false;
      deck.error = e.message || String(e);
      renderCaptainDeck();
    }
  }

  async function copyCaptainPlan() {
    const plan = state.captainDeck.plan;
    if (!plan) return;
    const text = JSON.stringify(plan, null, 2);
    try {
      await navigator.clipboard.writeText(text);
      const status = document.getElementById("captain-plan-status");
      if (status) status.textContent = "Plan copied to clipboard.";
    } catch (e) {
      prompt("Copy plan:", text);
    }
  }

  async function deployCaptainFirstPrompt() {
    const plan = state.activeCaptainPlan || state.captainDeck.plan;
    if (!plan || !plan.steps || !plan.steps.length) return;
    const current = currentCaptainStep(normalizeCaptainPlan(plan));
    if (!current) return;
    await dispatchCaptainStep(current.id || current.step_id);
  }

  async function loadAgents() {
    try {
      const data = await requestJson(`${MCH}/agents`);
      state.agents = data.agents || [];
      state.registryWriteEnabled = !!data.registry_write_enabled;
      renderRegisteredAgentCards();
      populateCaptainAgents();
      renderSettingsPanel();
      return data;
    } catch (e) {
      state.agents = [];
      state.registryWriteEnabled = false;
      renderRegisteredAgentCards();
      renderSettingsPanel();
      return null;
    }
  }

  async function refreshAgentStatuses() {
    const data = await requestJson(`${MCH}/agents/refresh-status`, { method: "POST" });
    state.agents = data.agents || [];
    state.agentStatusLastChecked = data.last_checked_at || null;
    state.registryWriteEnabled = !!data.registry_write_enabled;
    renderRegisteredAgentCards();
    populateCaptainAgents();
    renderSettingsPanel();
    return data;
  }

  async function loadAgentTemplates() {
    try {
      const data = await requestJson(`${MCH}/agents/templates`);
      state.agentTemplates = data.templates || [];
      return data;
    } catch (e) {
      state.agentTemplates = [];
      return null;
    }
  }

  function agentTypeLabel(agent) {
    if (!agent) return "Unknown";
    return agent.kind === "remote" ? "Remote" : "CLI";
  }

  function agentStatusLabel(agent) {
    if (!agent) return "unknown";
    if (agent.connection_status === "connected" && agent.status === "ready") return "connected";
    if (agent.status === "unverified" || agent.connection_status === "unverified") return "unverified";
    return agent.status || agent.connection_status || "unknown";
  }

  function setCodexStatusPill({ ready, disabled, label }) {
    const pill = document.getElementById("codex-status-pill");
    if (!pill) return;
    const text = label || (ready ? "READY" : disabled ? "DISABLED" : "COMING NEXT");
    pill.textContent = String(text).toUpperCase();
    pill.className = `status-pill ${ready ? "status-ready" : disabled ? "status-disabled" : "status-coming"}`;
  }

  function julesWorkspaceStatus() {
    const jules = (state.agents || []).find((agent) => agent.adapter === "jules_remote" && agent.user_created);
    if (!jules) return "Planning only";
    if (jules.connection_status === "connected" && jules.status === "ready") return "Connected";
    return "Setup needed";
  }

  function julesHeroStatus() {
    const jules = (state.agents || []).find((agent) => agent.adapter === "jules_remote" && agent.user_created);
    if (jules && jules.connection_status === "connected" && jules.status === "ready") return "Connected";
    return "Planning only";
  }

  function julesInspectorStatus() {
    const jules = (state.agents || []).find((agent) => agent.adapter === "jules_remote" && agent.user_created);
    if (jules && jules.connection_status === "connected" && jules.status === "ready") {
      return "Connected, planning only";
    }
    return "Setup needed";
  }

  function renderCodexCapabilityChips(codex) {
    const capsEl = document.getElementById("codex-capabilities");
    if (!capsEl) return;
    const caps = (codex && codex.capabilities) || [];
    if (!caps.length) {
      capsEl.style.display = "none";
      capsEl.innerHTML = "";
      return;
    }
    capsEl.style.display = "flex";
    capsEl.innerHTML = caps.slice(0, 4).map((cap) => `<span class="cap-chip">${escapeHtml(cap)}</span>`).join("");
  }

  function updateRunsEvidenceActions() {
    const hasSession = !!state.selectedThreadId;
    ["runs-open-monitor", "evidence-open-output"].forEach((id) => {
      const btn = document.getElementById(id);
      if (btn) btn.style.display = hasSession ? "" : "none";
    });
  }

  function formatHistoryTimestamp(value) {
    if (!value) return "—";
    try {
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) return value;
      return date.toLocaleString();
    } catch (e) {
      return value;
    }
  }

  function stepCompletionAllowed(step) {
    const gateStatus = step && step.gate_status;
    return !gateStatus || gateStatus === "approved";
  }

  function gateBannerCopy(step, { isCurrent = false } = {}) {
    if (!isCurrent || !step || !step.gate_status) return "";
    const label = step.gate_label || step.gate_status;
    if (step.gate_status === "blocked") {
      return `Hard stop — ${label}. Resolve the gate before continuing.`;
    }
    if (step.gate_status === "needs_more_evidence") {
      return "More evidence is required before this step can be marked done.";
    }
    if (step.gate_status === "pending") {
      return "Proof gate pending. Review and decide before marking the step done.";
    }
    if (step.gate_status === "approved") {
      return `Proof gate approved. You may mark the step done manually when ready.`;
    }
    return `Proof gate: ${label}`;
  }

  const TIMELINE_FILTER_KINDS = {
    plans: new Set(["plan_created", "step_dispatched", "step_completed", "step_revised", "plan_stopped"]),
    runs: new Set(["run_created"]),
    evidence: new Set(["evidence_saved"]),
    gates: new Set(["gate_created", "gate_approved", "gate_blocked", "gate_needs_more_evidence"]),
  };

  function worklogStatusClass(status) {
    const normalized = String(status || "").toLowerCase();
    if (normalized === "running" || normalized === "dispatched") return "status-ready";
    if (normalized === "completed" || normalized === "saved" || normalized === "approved") return "status-connected";
    if (normalized === "stopped" || normalized === "blocked" || normalized === "failed") return "status-disabled";
    return "status-coming";
  }

  function filteredMissionTimelineItems() {
    const items = state.missionWorklog || [];
    const filter = state.missionTimelineFilter || "all";
    if (filter === "all") return items;
    const allowed = TIMELINE_FILTER_KINDS[filter];
    if (!allowed) return items;
    return items.filter((item) => allowed.has(String(item.kind || "")));
  }

  function missionTimelineEmptyMessage() {
    const filter = state.missionTimelineFilter || "all";
    const hasAny = (state.missionWorklog || []).length > 0;
    if (!hasAny) return "No mission activity yet. Create a plan to start the timeline.";
    if (filter === "plans") return "No plan events yet. Captain plan activity will appear here.";
    if (filter === "runs") return "No run events yet. Dispatched agent runs will appear here.";
    if (filter === "evidence") return "No evidence events yet. Saved outputs will appear here.";
    if (filter === "gates") return "No gate events yet. Proof gate decisions will appear here.";
    return "No timeline events match this filter.";
  }

  function renderMissionTimelineFilter() {
    const bar = document.getElementById("mission-timeline-filter");
    if (!bar) return;
    bar.querySelectorAll("[data-timeline-filter]").forEach((button) => {
      const value = button.getAttribute("data-timeline-filter") || "all";
      button.classList.toggle("active", value === (state.missionTimelineFilter || "all"));
    });
  }

  function controlRoomHandlesMissionTimeline() {
    return !!document.getElementById("cr-command-center");
  }

  function renderMissionWorklog() {
    const list = document.getElementById("mission-worklog-list");
    const empty = document.getElementById("mission-worklog-empty");
    if (!list || !empty) return;
    if (controlRoomHandlesMissionTimeline()) {
      list.innerHTML = "";
      list.style.display = "none";
      empty.style.display = "none";
      return;
    }
    const allItems = state.missionWorklog || [];
    const items = filteredMissionTimelineItems();
    renderMissionTimelineFilter();
    if (!allItems.length) {
      list.innerHTML = "";
      list.style.display = "none";
      empty.style.display = "";
      empty.textContent = missionTimelineEmptyMessage();
      return;
    }
    if (!items.length) {
      list.innerHTML = "";
      list.style.display = "none";
      empty.style.display = "";
      empty.textContent = missionTimelineEmptyMessage();
      return;
    }
    empty.style.display = "none";
    list.style.display = "flex";
    list.innerHTML = items.map((item) => {
      const links = item.links || {};
      const linkBits = [];
      if (links.run_id) linkBits.push(`<button type="button" class="btn" data-worklog-run-id="${escapeHtml(links.run_id)}">Run</button>`);
      if (links.evidence_id) linkBits.push(`<button type="button" class="btn" data-worklog-evidence-id="${escapeHtml(links.evidence_id)}">Evidence</button>`);
      return `
        <div class="worklog-event-card" data-testid="worklog-event-${escapeHtml(item.kind || "event")}">
          <div class="worklog-event-top">
            <span class="worklog-event-label">${escapeHtml(item.label || item.kind || "event")}</span>
            <span class="status-pill ${worklogStatusClass(item.status)}">${escapeHtml(String(item.status || "saved").toUpperCase())}</span>
          </div>
          <p class="worklog-event-title">${escapeHtml(item.title || "Mission activity")}</p>
          <p class="worklog-event-summary">${escapeHtml(item.summary || "")}</p>
          <p class="worklog-event-time">${escapeHtml(formatHistoryTimestamp(item.created_at))}</p>
          ${linkBits.length ? `<div class="worklog-event-links">${linkBits.join("")}</div>` : ""}
        </div>
      `;
    }).join("");
    list.querySelectorAll("[data-worklog-run-id]").forEach((button) => {
      button.addEventListener("click", () => {
        const runId = button.getAttribute("data-worklog-run-id");
        if (runId) openRunDetailModal(runId).catch((e) => console.error(e));
      });
    });
    list.querySelectorAll("[data-worklog-evidence-id]").forEach((button) => {
      button.addEventListener("click", () => {
        const evidenceId = button.getAttribute("data-worklog-evidence-id");
        if (evidenceId) openEvidenceDetailModal(evidenceId).catch((e) => console.error(e));
      });
    });
  }

  async function loadMissionWorklog() {
    try {
      const data = await requestJson(`${MCH}/worklog/recent`);
      state.missionWorklog = data.items || [];
      renderMissionWorklog();
      return data;
    } catch (e) {
      state.missionWorklog = [];
      renderMissionWorklog();
      return null;
    }
  }

  function renderRunsPanel() {
    const list = document.getElementById("runs-list");
    const empty = document.querySelector("[data-testid='runs-empty-state']");
    const runs = state.recentRuns || [];
    if (!list || !empty) return;
    if (!runs.length) {
      list.style.display = "none";
      list.innerHTML = "";
      empty.style.display = "";
      return;
    }
    empty.style.display = "none";
    list.style.display = "grid";
    list.innerHTML = runs.map((run) => `
      <div class="history-card" data-run-id="${escapeHtml(run.run_id)}">
        <div class="history-card-top">
          <h3 class="history-card-title">${escapeHtml(run.title || run.run_id)}</h3>
          <span class="status-pill ${run.status === "running" || run.status === "dispatched" ? "status-ready" : "status-connected"}">${escapeHtml((run.status || "unknown").toUpperCase())}</span>
        </div>
        <p class="history-card-meta">${escapeHtml(run.agent_id || "agent")} · ${escapeHtml(run.repo_id || "repo")} · ${escapeHtml(formatHistoryTimestamp(run.started_at))}${run.plan_id ? ` · Plan ${escapeHtml(run.plan_id)}` : ""}</p>
        <p class="history-card-copy">${escapeHtml(run.prompt_excerpt || "No prompt excerpt saved.")}</p>
        <p class="history-card-meta">Evidence: ${Number(run.evidence_count || 0)}${run.gate_status ? ` · Gate: ${escapeHtml(run.gate_status)}` : ""}</p>
        <button type="button" class="btn" data-view-run-id="${escapeHtml(run.run_id)}">View Run</button>
      </div>
    `).join("");
    list.querySelectorAll("[data-view-run-id]").forEach((button) => {
      button.addEventListener("click", () => {
        const runId = button.getAttribute("data-view-run-id");
        if (runId) openRunDetailModal(runId).catch((e) => console.error(e));
      });
    });
  }

  function filteredEvidenceItems() {
    const evidence = state.recentEvidence || [];
    const filter = state.evidenceTypeFilter || "all";
    if (filter === "all") return evidence;
    return evidence.filter((item) => String(item.type || "") === filter);
  }

  function renderEvidenceTypeFilter() {
    const bar = document.getElementById("evidence-type-filter");
    if (!bar) return;
    const hasEvidence = (state.recentEvidence || []).length > 0;
    bar.style.display = hasEvidence ? "flex" : "none";
    bar.querySelectorAll("[data-evidence-filter]").forEach((button) => {
      const value = button.getAttribute("data-evidence-filter") || "all";
      button.classList.toggle("active", value === (state.evidenceTypeFilter || "all"));
    });
  }

  function renderEvidencePanel() {
    const list = document.getElementById("evidence-list");
    const empty = document.querySelector("[data-testid='evidence-empty-state']");
    const evidence = filteredEvidenceItems();
    if (!list || !empty) return;
    renderEvidenceTypeFilter();
    if (!evidence.length) {
      list.style.display = "none";
      list.innerHTML = "";
      empty.style.display = (state.recentEvidence || []).length ? "none" : "";
      if ((state.recentEvidence || []).length) {
        list.style.display = "grid";
        list.innerHTML = "<p class=\"history-card-copy\">No evidence matches this filter.</p>";
      }
      return;
    }
    empty.style.display = "none";
    list.style.display = "grid";
    list.innerHTML = evidence.map((item) => `
      <div class="history-card" data-evidence-id="${escapeHtml(item.evidence_id)}">
        <div class="history-card-top">
          <h3 class="history-card-title">${escapeHtml(item.title || item.evidence_id)}</h3>
          <span class="status-pill status-connected">${escapeHtml((item.type || "evidence").toUpperCase())}</span>
        </div>
        <p class="history-card-meta">${escapeHtml(formatHistoryTimestamp(item.created_at))}${item.agent_id ? ` · ${escapeHtml(item.agent_id)}` : ""}${item.run_id ? ` · Run ${escapeHtml(item.run_id)}` : ""}</p>
        <p class="history-card-copy">${escapeHtml(item.summary || item.content_excerpt || "Saved evidence excerpt.")}</p>
        <button type="button" class="btn" data-view-evidence-id="${escapeHtml(item.evidence_id)}">View Evidence</button>
      </div>
    `).join("");
    list.querySelectorAll("[data-view-evidence-id]").forEach((button) => {
      button.addEventListener("click", () => {
        const evidenceId = button.getAttribute("data-view-evidence-id");
        if (evidenceId) openEvidenceDetailModal(evidenceId).catch((e) => console.error(e));
      });
    });
  }

  async function loadRecentRuns() {
    try {
      const data = await requestJson(`${MCH}/runs/recent`);
      state.recentRuns = data.runs || [];
      renderRunsPanel();
      return data;
    } catch (e) {
      state.recentRuns = [];
      renderRunsPanel();
      return null;
    }
  }

  async function loadRecentEvidence() {
    try {
      const data = await requestJson(`${MCH}/evidence/recent`);
      state.recentEvidence = data.evidence || [];
      renderEvidencePanel();
      return data;
    } catch (e) {
      state.recentEvidence = [];
      renderEvidencePanel();
      return null;
    }
  }

  async function exportRunReport(runId) {
    const data = await requestJson(`${MCH}/runs/${encodeURIComponent(runId)}/report`);
    const markdown = data.markdown || "";
    const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `warden-run-${runId}.md`;
    link.click();
    URL.revokeObjectURL(url);
    if (navigator.clipboard && navigator.clipboard.writeText) {
      try {
        await navigator.clipboard.writeText(markdown);
      } catch (e) {
        /* clipboard optional */
      }
    }
  }

  function proofGateStatusClass(status) {
    const normalized = String(status || "").toLowerCase();
    if (normalized === "approved") return "status-connected";
    if (normalized === "pending") return "status-coming";
    return "status-disabled";
  }

  function renderProofGateCard(gate, { interactive = false } = {}) {
    const status = gate.status || "pending";
    const actions = interactive && status === "pending"
      ? `
        <div class="proof-gate-actions">
          <button type="button" class="btn good" data-gate-approve="${escapeHtml(gate.gate_id)}">Approve</button>
          <button type="button" class="btn bad" data-gate-block="${escapeHtml(gate.gate_id)}">Block</button>
          <button type="button" class="btn" data-gate-more-evidence="${escapeHtml(gate.gate_id)}">Request More Evidence</button>
        </div>
      `
      : gate.decision_reason
        ? `<p class="history-card-meta">Decision: ${escapeHtml(gate.decision_reason)}</p>`
        : "";
    return `
      <div class="proof-gate-card" data-gate-id="${escapeHtml(gate.gate_id)}">
        <div class="history-card-top">
          <h4 class="history-card-title">${escapeHtml(gate.title || gate.gate_id)}</h4>
          <span class="status-pill ${proofGateStatusClass(status)}">${escapeHtml(String(status).toUpperCase())}</span>
        </div>
        <p class="history-card-meta">${escapeHtml(gate.gate_type || "manual_review")} · ${escapeHtml(formatHistoryTimestamp(gate.created_at))}</p>
        <p class="history-card-copy">${escapeHtml(gate.summary || "Manual proof gate.")}</p>
        ${actions}
      </div>
    `;
  }

  function bindProofGateActions(container, runId) {
    if (!container) return;
    container.querySelectorAll("[data-gate-approve]").forEach((button) => {
      button.addEventListener("click", () => {
        const gateId = button.getAttribute("data-gate-approve");
        if (gateId) decideProofGate(gateId, "approve", runId).catch((e) => console.error(e));
      });
    });
    container.querySelectorAll("[data-gate-block]").forEach((button) => {
      button.addEventListener("click", () => {
        const gateId = button.getAttribute("data-gate-block");
        if (gateId) decideProofGate(gateId, "block", runId).catch((e) => console.error(e));
      });
    });
    container.querySelectorAll("[data-gate-more-evidence]").forEach((button) => {
      button.addEventListener("click", () => {
        const gateId = button.getAttribute("data-gate-more-evidence");
        if (gateId) decideProofGate(gateId, "request_more_evidence", runId).catch((e) => console.error(e));
      });
    });
  }

  async function decideProofGate(gateId, decision, runId) {
    let decisionReason = null;
    if (decision === "block" || decision === "request_more_evidence") {
      decisionReason = window.prompt("Enter a short reason for this decision:");
      if (!decisionReason || !decisionReason.trim()) return;
    }
    await requestJson(`${MCH}/gates/${encodeURIComponent(gateId)}/decision`, {
      method: "POST",
      body: {
        decision,
        decided_by: "operator",
        decision_reason: decisionReason,
      },
    });
    if (runId) await openRunDetailModal(runId);
    await Promise.all([loadRecentGates(), loadMissionWorklog(), loadActiveCaptainPlan()]);
  }

  async function createProofGateForRun(runId, evidenceIds) {
    const title = window.prompt("Proof gate title:", "Manual review gate");
    if (!title || !title.trim()) return;
    await requestJson(`${MCH}/runs/${encodeURIComponent(runId)}/gates`, {
      method: "POST",
      body: {
        title: title.trim(),
        summary: "Operator-created manual proof gate.",
        evidence_ids: evidenceIds || [],
      },
    });
    await openRunDetailModal(runId);
    await Promise.all([loadRecentGates(), loadMissionWorklog(), loadActiveCaptainPlan()]);
  }

  function renderInspectorGatesSummary() {
    const summary = document.getElementById("inspector-gates-summary");
    if (!summary) return;
    const gates = state.recentGates || [];
    if (!gates.length) {
      summary.textContent = "No proof gates yet.";
      return;
    }
    const pending = gates.filter((gate) => gate.status === "pending").length;
    const latest = gates[0];
    summary.innerHTML = `
      <div>${pending} pending · ${gates.length} total</div>
      <div class="history-card-meta">Latest: ${escapeHtml(latest.title || latest.gate_id)} (${escapeHtml(latest.status || "pending")})</div>
    `;
  }

  async function loadRecentGates() {
    try {
      const data = await requestJson(`${MCH}/gates/recent`);
      state.recentGates = data.gates || [];
      renderInspectorGatesSummary();
      return data;
    } catch (e) {
      state.recentGates = [];
      renderInspectorGatesSummary();
      return null;
    }
  }

  function runDetailDecisionLabel(decision) {
    const labels = {
      approve: "Approved",
      block: "Blocked",
      request_more_evidence: "Requested more evidence",
    };
    return labels[decision] || String(decision || "decision").replace(/_/g, " ");
  }

  function linkedCaptainStepForRun(run) {
    const plan = state.activeCaptainPlan;
    if (!plan || !run) return null;
    const runId = String(run.run_id || "");
    if (!runId) return null;
    return (plan.steps || []).find((step) => String(step.run_id || "") === runId) || null;
  }

  function renderRunDetailDecisions(gates) {
    const decisionsEl = document.getElementById("run-detail-decisions");
    if (!decisionsEl) return;
    const entries = [];
    gates.forEach((gate) => {
      (gate.decision_log || []).forEach((entry) => {
        entries.push({
          at: entry.at,
          gateTitle: gate.title || gate.gate_id,
          decision: entry.decision,
          decidedBy: entry.decided_by,
          reason: entry.reason,
        });
      });
    });
    entries.sort((a, b) => String(b.at || "").localeCompare(String(a.at || "")));
    if (!entries.length) {
      decisionsEl.innerHTML = "<li>No gate decisions recorded yet.</li>";
      return;
    }
    decisionsEl.innerHTML = entries.map((entry) => {
      const reason = entry.reason ? ` — ${entry.reason}` : "";
      return `<li>${escapeHtml(runDetailDecisionLabel(entry.decision))} · ${escapeHtml(entry.gateTitle)} · ${escapeHtml(entry.decidedBy || "operator")}${escapeHtml(reason)} · ${escapeHtml(formatHistoryTimestamp(entry.at))}</li>`;
    }).join("");
  }

  function renderRunDetailNextActions(run, gates, evidenceItems, { canWrite = false } = {}) {
    const actionsEl = document.getElementById("run-detail-next-actions");
    if (!actionsEl) return;
    const gateStatus = run.gate_status || (gates.length ? gates[0].status : null);
    const pendingGate = gates.find((gate) => gate.status === "pending");
    const linkedStep = linkedCaptainStepForRun(run);
    const evidenceIds = evidenceItems.map((item) => item.evidence_id).filter(Boolean);
    const bits = [];

    if (!canWrite) {
      bits.push('<p class="run-detail-action-note">Manual review actions require the private runner service.</p>');
    } else if (gateStatus === "blocked") {
      bits.push('<p class="run-detail-action-note">Hard stop — gate is blocked. Revise the step or resolve the gate before continuing.</p>');
    } else if (!gates.length) {
      bits.push('<button type="button" class="btn primary" data-testid="run-detail-create-gate" id="run-detail-create-gate">Create Proof Gate</button>');
    } else if (pendingGate) {
      bits.push(`
        <button type="button" class="btn good" data-testid="run-detail-approve-gate" data-gate-approve="${escapeHtml(pendingGate.gate_id)}">Approve Gate</button>
        <button type="button" class="btn bad" data-testid="run-detail-block-gate" data-gate-block="${escapeHtml(pendingGate.gate_id)}">Block Gate</button>
        <button type="button" class="btn" data-testid="run-detail-more-evidence" data-gate-more-evidence="${escapeHtml(pendingGate.gate_id)}">Request More Evidence</button>
      `);
    } else if (gateStatus === "needs_more_evidence") {
      bits.push('<p class="run-detail-action-note">Save more evidence, then approve the gate when ready.</p>');
      bits.push('<button type="button" class="btn" data-testid="run-detail-create-gate" id="run-detail-create-gate">Create Proof Gate</button>');
    } else if (gateStatus === "approved") {
      bits.push('<p class="run-detail-action-note">Gate approved. Mark the linked Captain step done manually when ready — no auto-dispatch.</p>');
      if (linkedStep && stepCompletionAllowed(linkedStep)) {
        bits.push(`<button type="button" class="btn good" data-testid="run-detail-complete-step" data-complete-step-id="${escapeHtml(linkedStep.id || linkedStep.step_id)}">Mark Step Complete</button>`);
      }
    } else {
      bits.push('<button type="button" class="btn primary" data-testid="run-detail-create-gate" id="run-detail-create-gate">Create Proof Gate</button>');
    }

    actionsEl.innerHTML = bits.join("");
    actionsEl.dataset.gateStatus = gateStatus || "none";

    const createGateBtn = actionsEl.querySelector("#run-detail-create-gate");
    if (createGateBtn) {
      createGateBtn.addEventListener("click", () => {
        createProofGateForRun(run.run_id, evidenceIds).catch((e) => console.error(e));
      });
    }
    bindProofGateActions(actionsEl, run.run_id);
    actionsEl.querySelectorAll("[data-complete-step-id]").forEach((button) => {
      button.addEventListener("click", () => {
        const stepId = button.getAttribute("data-complete-step-id");
        if (stepId) completeCaptainStep(stepId).catch((e) => console.error(e));
      });
    });
  }

  async function openRunDetailModal(runId) {
    const modal = document.getElementById("run-detail-modal");
    if (!modal) return;
    const [data, gateData] = await Promise.all([
      requestJson(`${MCH}/runs/${encodeURIComponent(runId)}`),
      requestJson(`${MCH}/runs/${encodeURIComponent(runId)}/gates`).catch(() => ({ gates: [] })),
    ]);
    const run = data.run || {};
    const gates = gateData.gates || data.gates || [];
    state.activeRunDetailId = runId;
    const title = document.getElementById("run-detail-title");
    const meta = document.getElementById("run-detail-meta");
    const prompt = document.getElementById("run-detail-prompt");
    const transcript = document.getElementById("run-detail-transcript");
    const evidence = document.getElementById("run-detail-evidence");
    const gatesEl = document.getElementById("run-detail-gates");
    const health = state.health || {};
    const canWrite = !!health.tmux_runner_enabled && !!health.codex_runner_enabled;
    if (title) title.textContent = run.title || run.run_id || "Run Detail";
    if (meta) {
      const gateLabel = run.gate_label || (run.gate_status ? String(run.gate_status).replace(/_/g, " ") : "No gate");
      meta.textContent = `${run.agent_id || "agent"} · ${run.status || "unknown"} · ${formatHistoryTimestamp(run.started_at)} · Evidence: ${Number(run.evidence_count || (data.evidence || []).length || 0)} · Gate: ${gateLabel}`;
    }
    const gateStateEl = document.getElementById("run-detail-gate-state");
    if (gateStateEl) {
      const gateStatus = run.gate_status || (gates.length ? gates[0].status : null);
      const gateLabel = run.gate_label || (gateStatus ? String(gateStatus).replace(/_/g, " ") : "No gate");
      let copy = `Proof gate state: ${gateLabel}`;
      if (gateStatus === "blocked") copy = `Hard stop — ${gateLabel}. This run cannot advance until the gate is resolved.`;
      if (gateStatus === "needs_more_evidence") copy = "This run needs more evidence before the step can be marked done.";
      if (gateStatus === "pending") copy = "Proof gate pending. Review evidence and decide before marking the step done.";
      gateStateEl.textContent = copy;
      gateStateEl.dataset.gateStatus = gateStatus || "none";
    }
    if (prompt) prompt.textContent = run.prompt || run.prompt_excerpt || "(no prompt saved)";
    if (transcript) transcript.textContent = run.transcript_excerpt || "(no transcript saved yet)";
    const evidenceItems = data.evidence || [];
    if (evidence) {
      evidence.innerHTML = evidenceItems.length
        ? evidenceItems.map((item) => `<li>${escapeHtml(item.title || item.evidence_id)} · ${escapeHtml(item.type || "evidence")}</li>`).join("")
        : "<li>No saved evidence linked to this run yet.</li>";
    }
    if (gatesEl) {
      gatesEl.innerHTML = gates.length
        ? gates.map((gate) => renderProofGateCard(gate, { interactive: false })).join("")
        : "<p class=\"history-card-copy\">No proof gate created for this run yet.</p>";
    }
    renderRunDetailDecisions(gates);
    renderRunDetailNextActions(run, gates, evidenceItems, { canWrite });
    const exportBtn = document.getElementById("run-detail-export");
    if (exportBtn) {
      exportBtn.onclick = () => exportRunReport(runId).catch((e) => console.error(e));
    }
    modal.style.display = "flex";
  }

  function closeRunDetailModal() {
    const modal = document.getElementById("run-detail-modal");
    if (modal) modal.style.display = "none";
  }

  async function openEvidenceDetailModal(evidenceId) {
    const modal = document.getElementById("evidence-detail-modal");
    if (!modal) return;
    const data = await requestJson(`${MCH}/evidence/${encodeURIComponent(evidenceId)}`);
    const item = data.evidence || {};
    const linkedRun = data.linked_run;
    const title = document.getElementById("evidence-detail-title");
    const meta = document.getElementById("evidence-detail-meta");
    const content = document.getElementById("evidence-detail-content");
    const runMeta = document.getElementById("evidence-detail-run");
    if (title) title.textContent = item.title || item.evidence_id || "Evidence Detail";
    if (meta) {
      meta.textContent = `${item.type || "evidence"} · ${formatHistoryTimestamp(item.created_at)} · ${item.source || "operator"}`;
    }
    if (content) content.textContent = item.content || item.content_excerpt || item.summary || "(no content saved)";
    if (runMeta) {
      runMeta.textContent = linkedRun
        ? `Linked run: ${linkedRun.title || linkedRun.run_id} (${linkedRun.status || "unknown"})`
        : "No linked run.";
    }
    modal.style.display = "flex";
  }

  function closeEvidenceDetailModal() {
    const modal = document.getElementById("evidence-detail-modal");
    if (modal) modal.style.display = "none";
  }

  function normalizeCaptainPlan(plan) {
    if (!plan) return null;
    const steps = (plan.steps || []).map((step, index) => ({
      id: step.id || step.step_id || `step_${index + 1}`,
      step_id: step.step_id || step.id || `step_${index + 1}`,
      title: step.title,
      agent: step.agent || step.agent_id || "codex_cli",
      agent_id: step.agent_id || step.agent || "codex_cli",
      prompt: step.prompt || step.prompt_preview || "",
      status: step.status || "queued",
      run_id: step.run_id || null,
      evidence_ids: step.evidence_ids || [],
      order: step.order || index + 1,
    }));
    return {
      ...plan,
      plan_id: plan.plan_id || plan.id,
      current_step_id: plan.current_step_id || (steps[0] && steps[0].id),
      steps,
    };
  }

  function setActiveCaptainPlan(plan) {
    state.activeCaptainPlan = normalizeCaptainPlan(plan);
    if (state.captainDeck && state.activeCaptainPlan) {
      state.captainDeck.plan = state.activeCaptainPlan;
    }
    renderMissionPlanPanel();
    renderCaptainDeck();
  }

  function currentCaptainStep(plan) {
    if (!plan || !plan.steps || !plan.steps.length) return null;
    const currentId = plan.current_step_id;
    return plan.steps.find((step) => step.id === currentId || step.step_id === currentId) || plan.steps[0];
  }

  function isControlRoomDemoMode() {
    return !!(window.WardenControlRoom && window.WardenControlRoom.isDemoMode && window.WardenControlRoom.isDemoMode());
  }

  function renderMissionPlanPanel() {
    const empty = document.getElementById("current-mission-empty");
    const panel = document.getElementById("current-mission-plan");
    const header = document.getElementById("current-plan-header");
    const stepsEl = document.getElementById("captain-plan-steps");
    const controls = document.getElementById("captain-plan-controls");
    const plan = state.activeCaptainPlan;
    if (!empty || !panel || !header || !stepsEl || !controls) return;

    if (isControlRoomDemoMode()) {
      empty.style.display = "none";
      panel.style.display = "none";
      return;
    }

    const crEmpty = document.getElementById("cr-mission-empty");
    const crActive = document.getElementById("cr-mission-active");
    if (!plan || plan.status === "stopped") {
      empty.style.display = "";
      panel.style.display = "none";
      if (crEmpty) crEmpty.style.display = "";
      if (crActive) crActive.style.display = "none";
      return;
    }

    empty.style.display = "none";
    panel.style.display = "";
    if (crEmpty) crEmpty.style.display = "none";
    if (crActive) crActive.style.display = "none";
    const current = currentCaptainStep(plan);
    const currentGateBanner = gateBannerCopy(current, { isCurrent: true });
    header.innerHTML = `
      <strong>${escapeHtml(plan.title || "Captain plan")}</strong>
      <div>${escapeHtml(plan.summary || "")}</div>
      <div>Status: ${escapeHtml(plan.status || "active")} · Repo: ${escapeHtml(plan.repo_id || "n/a")}</div>
      ${current && current.gate_label ? `<div data-testid="current-step-gate-label">Gate: ${escapeHtml(current.gate_label)}</div>` : ""}
      ${currentGateBanner ? `<p class="captain-gate-banner" data-testid="captain-step-gate-banner">${escapeHtml(currentGateBanner)}</p>` : ""}
    `;

    stepsEl.innerHTML = (plan.steps || []).map((step) => {
      const isCurrent = current && (step.id === current.id || step.step_id === current.step_id);
      const status = step.status || "queued";
      const classes = ["captain-plan-step-card", isCurrent ? "current" : "", status === "passed" ? "passed" : ""].filter(Boolean).join(" ");
      const links = [];
      if (step.run_id) links.push(`<button type="button" class="btn" data-view-step-run="${escapeHtml(step.run_id)}">View Run</button>`);
      if ((step.evidence_ids || []).length) {
        links.push(`<button type="button" class="btn" data-view-step-evidence="${escapeHtml(step.evidence_ids[0])}">View Evidence</button>`);
      }
      const canComplete = stepCompletionAllowed(step);
      const actionRow = isCurrent && plan.status === "active" ? `
        <div class="captain-plan-step-actions" data-testid="captain-step-actions-${escapeHtml(step.id)}">
          <button type="button" class="btn primary" data-deploy-step-id="${escapeHtml(step.id)}">${escapeHtml(deployStepButtonLabel(plan, step))}</button>
          <button type="button" class="btn good" data-complete-step-id="${escapeHtml(step.id)}" ${canComplete ? "" : "disabled"}>Mark Step Done</button>
          <button type="button" class="btn" data-revise-step-id="${escapeHtml(step.id)}">Revise Step</button>
        </div>
      ` : links.join("");
      const stepGateBanner = gateBannerCopy(step, { isCurrent });
      return `
        <div class="${classes}" data-step-id="${escapeHtml(step.id)}">
          <div class="captain-plan-step-top">
            <h4 class="captain-plan-step-title">${escapeHtml(step.title || step.id)}</h4>
            <span class="status-pill ${status === "passed" ? "status-ready" : isCurrent ? "status-connected" : "status-coming"}">${escapeHtml(status.toUpperCase())}</span>
          </div>
          <p class="captain-plan-step-meta">${escapeHtml(step.agent || "codex_cli")}${step.run_id ? ` · Run ${escapeHtml(step.run_id)}` : ""}${step.gate_label ? ` · ${escapeHtml(step.gate_label)}` : ""}</p>
          ${stepGateBanner && !isCurrent ? `<p class="captain-gate-banner">${escapeHtml(stepGateBanner)}</p>` : ""}
          <p class="captain-plan-step-prompt-preview">${escapeHtml((step.prompt || "").slice(0, 220))}${(step.prompt || "").length > 220 ? "..." : ""}</p>
          ${actionRow}
        </div>
      `;
    }).join("");

    controls.innerHTML = plan.status === "active"
      ? `<button type="button" class="btn bad" id="captain-stop-plan" data-testid="captain-stop-plan">Stop Plan</button>`
      : "";

    stepsEl.querySelectorAll("[data-deploy-step-id]").forEach((button) => {
      button.addEventListener("click", () => {
        const stepId = button.getAttribute("data-deploy-step-id");
        if (stepId) dispatchCaptainStep(stepId).catch((e) => console.error(e));
      });
    });
    stepsEl.querySelectorAll("[data-complete-step-id]").forEach((button) => {
      button.addEventListener("click", () => {
        const stepId = button.getAttribute("data-complete-step-id");
        if (stepId) completeCaptainStep(stepId).catch((e) => console.error(e));
      });
    });
    stepsEl.querySelectorAll("[data-revise-step-id]").forEach((button) => {
      button.addEventListener("click", () => {
        const stepId = button.getAttribute("data-revise-step-id");
        if (stepId) reviseCaptainStep(stepId).catch((e) => console.error(e));
      });
    });
    stepsEl.querySelectorAll("[data-view-step-run]").forEach((button) => {
      button.addEventListener("click", () => {
        const runId = button.getAttribute("data-view-step-run");
        if (runId) openRunDetailModal(runId).catch((e) => console.error(e));
      });
    });
    stepsEl.querySelectorAll("[data-view-step-evidence]").forEach((button) => {
      button.addEventListener("click", () => {
        const evidenceId = button.getAttribute("data-view-step-evidence");
        if (evidenceId) openEvidenceDetailModal(evidenceId).catch((e) => console.error(e));
      });
    });
    const stopBtn = document.getElementById("captain-stop-plan");
    if (stopBtn) {
      stopBtn.addEventListener("click", () => stopCaptainPlan().catch((e) => console.error(e)));
    }

  }

  function deployStepButtonLabel(plan, step) {
    const steps = plan.steps || [];
    const index = steps.findIndex((item) => item.id === step.id);
    const priorPassed = index > 0 && steps.slice(0, index).every((item) => item.status === "passed");
    if (priorPassed && (step.status === "queued" || step.status === "revised")) return "Deploy Next Step";
    return "Deploy Current Step";
  }

  async function loadActiveCaptainPlan() {
    try {
      const data = await requestJson(`${MCH}/captain/plans/recent`);
      const plans = (data.plans || []).map(normalizeCaptainPlan);
      const active = plans.find((plan) => plan.status === "active") || plans[0] || null;
      if (active && active.plan_id) {
        const detail = await requestJson(`${MCH}/captain/plans/${encodeURIComponent(active.plan_id)}`);
        setActiveCaptainPlan(detail.plan || active);
      } else {
        setActiveCaptainPlan(null);
      }
      if (isControlRoomDemoMode() && window.WardenControlRoom && window.WardenControlRoom.refresh) {
        await window.WardenControlRoom.refresh({ quiet: true });
      }
      return active;
    } catch (e) {
      setActiveCaptainPlan(null);
      if (isControlRoomDemoMode() && window.WardenControlRoom && window.WardenControlRoom.refresh) {
        await window.WardenControlRoom.refresh({ quiet: true });
      }
      return null;
    }
  }

  async function dispatchCaptainStep(stepId) {
    const plan = state.activeCaptainPlan;
    if (!plan || !plan.plan_id) return;
    const step = (plan.steps || []).find((item) => item.id === stepId || item.step_id === stepId);
    if (!step) return;
    const result = await requestJson(`${MCH}/captain/plans/${encodeURIComponent(plan.plan_id)}/steps/${encodeURIComponent(stepId)}/dispatch`, {
      method: "POST",
    });
    if (result.plan) setActiveCaptainPlan(result.plan);
    const dispatch = result.dispatch || {};
    state.selectedThreadId = dispatch.session_id || state.selectedThreadId;
    state.activeWardenRunId = dispatch.runner_id || state.activeWardenRunId;
    await Promise.all([loadRecentRuns(), loadMissionWorklog()]);
    closeCaptainDeckModal();
    openLiveCLIMonitor();
    const prompt = dispatch.prompt || step.prompt;
    if (dispatch.session_id && prompt) {
      setTimeout(async () => {
        try {
          await requestJson(`${MCH}/sessions/${encodeURIComponent(dispatch.session_id)}/runner/send-prompt`, {
            method: "POST",
            body: { prompt },
          });
          setQuickReplyStatus("Prompt sent to Codex.");
          await refreshLiveMonitor();
        } catch (e) {
          await refreshLiveMonitor();
        }
      }, 10000);
    }
  }

  async function completeCaptainStep(stepId) {
    const plan = state.activeCaptainPlan;
    if (!plan || !plan.plan_id) return;
    const evidenceIds = state.activeWardenRunId ? [] : [];
    const result = await requestJson(`${MCH}/captain/plans/${encodeURIComponent(plan.plan_id)}/steps/${encodeURIComponent(stepId)}/complete`, {
      method: "POST",
      body: { evidence_ids: evidenceIds },
    });
    if (result.plan) setActiveCaptainPlan(result.plan);
    await loadMissionWorklog();
  }

  async function reviseCaptainStep(stepId) {
    const plan = state.activeCaptainPlan;
    if (!plan || !plan.plan_id) return;
    const step = (plan.steps || []).find((item) => item.id === stepId || item.step_id === stepId);
    if (!step) return;
    const revisedPrompt = window.prompt("Revise step prompt:", step.prompt || "");
    if (revisedPrompt === null) return;
    const result = await requestJson(`${MCH}/captain/plans/${encodeURIComponent(plan.plan_id)}/steps/${encodeURIComponent(stepId)}/revise`, {
      method: "POST",
      body: { prompt: revisedPrompt, note: "Operator revised the step prompt." },
    });
    if (result.plan) setActiveCaptainPlan(result.plan);
    await loadMissionWorklog();
  }

  async function stopCaptainPlan() {
    const plan = state.activeCaptainPlan;
    if (!plan || !plan.plan_id) return;
    const result = await requestJson(`${MCH}/captain/plans/${encodeURIComponent(plan.plan_id)}/stop`, {
      method: "POST",
      body: { note: "Operator stopped the Captain plan." },
    });
    if (result.plan) setActiveCaptainPlan(result.plan);
    await loadMissionWorklog();
  }

  function renderSettingsPanel() {
    const deck = state.captainDeck;
    const health = state.health || {};
    const captainStatus = document.getElementById("settings-captain-status");
    const captainModel = document.getElementById("settings-captain-model");
    const captainKeySource = document.getElementById("settings-captain-key-source");
    const agentNote = document.getElementById("settings-agent-note");
    const publicRunner = document.getElementById("settings-public-runner");
    const privateRunner = document.getElementById("settings-private-runner");
    const shellInput = document.getElementById("settings-shell-input");
    const agentRegistration = document.getElementById("settings-agent-registration");
    const heroCaptain = document.getElementById("hero-captain-status");
    const heroCodex = document.getElementById("hero-codex-status");
    const heroJules = document.getElementById("hero-jules-status");
    const crPublic = document.getElementById("cr-public-runner");
    const crPrivate = document.getElementById("cr-private-runner");
    const crShell = document.getElementById("cr-shell-input");
    const crAgentReg = document.getElementById("cr-agent-registration");
    const settingsCodex = document.getElementById("settings-codex-status");
    const settingsJules = document.getElementById("settings-jules-status");
    const inspectorNextMove = document.getElementById("inspector-next-move-copy");
    const inspectorCaptain = document.getElementById("inspector-captain-agent");
    const inspectorCodex = document.getElementById("inspector-codex-agent");
    const inspectorJules = document.getElementById("inspector-jules-agent");
    const useCodexDirectly = document.getElementById("use-codex-directly");
    const inspectorViewCodex = document.getElementById("inspector-view-codex");
    const runnerActive = !!health.tmux_runner_enabled && !!health.codex_runner_enabled;
    const shellDisabled = !health.arbitrary_command_execution_enabled;
    const publicRunnerText = "Public runner: Disabled on public service";
    const privateRunnerText = runnerActive
      ? "Private runner: Active on this service"
      : "Private runner: Available only on private service";
    const shellText = shellDisabled ? "Arbitrary shell input: Disabled" : "Arbitrary shell input: Enabled";
    const agentRegText = state.registryWriteEnabled
      ? "Agent registration: Enabled on this service"
      : "Agent registration: Private only";
    if (captainStatus) {
      captainStatus.textContent = deck.configured
        ? `Captain: Configured${deck.keySource && deck.keySource !== "missing" ? ` (${deck.keySource})` : ""}`
        : "Captain: Not configured";
    }
    if (captainModel) {
      captainModel.textContent = `Model: ${deck.model || "openrouter/auto"}`;
    }
    if (captainKeySource) {
      captainKeySource.textContent = `Key source: ${deck.keySource || "missing"}`;
    }
    if (agentNote) {
      agentNote.textContent = state.registryWriteEnabled
        ? "Add and configure CLI or remote agents from the Agents section after connection checks."
        : "Agent registration is available on the private runner service (8125).";
    }
    if (publicRunner) publicRunner.textContent = publicRunnerText;
    if (privateRunner) privateRunner.textContent = privateRunnerText;
    if (shellInput) shellInput.textContent = shellText;
    if (agentRegistration) agentRegistration.textContent = agentRegText;
    if (heroCaptain) {
      heroCaptain.textContent = `Captain: ${deck.configured ? "Ready" : "Not configured"}`;
    }
    if (heroCodex) heroCodex.textContent = `Codex: ${runnerActive ? "Ready" : "Disabled"}`;
    if (heroJules) heroJules.textContent = `Jules: ${julesHeroStatus()}`;
    if (settingsCodex) {
      settingsCodex.textContent = runnerActive ? "Codex CLI: Ready on this service" : "Codex CLI: Disabled on this service";
    }
    if (settingsJules) {
      const jules = (state.agents || []).find((agent) => agent.adapter === "jules_remote" && agent.user_created);
      if (!jules) {
        settingsJules.textContent = "Jules Remote: Not configured";
      } else if (jules.connection_status === "connected" && jules.status === "ready") {
        settingsJules.textContent = "Jules Remote: Connected — planning and status only";
      } else {
        settingsJules.textContent = "Jules Remote: Setup needed";
      }
    }
    if (crPublic) crPublic.textContent = "Public runner: Disabled";
    if (crPrivate) {
      crPrivate.textContent = runnerActive
        ? "Private runner: Active on this service"
        : "Private runner: Unavailable on this service";
    }
    if (crShell) crShell.textContent = shellDisabled ? "Arbitrary shell input: Disabled" : "Arbitrary shell input: Enabled";
    if (crAgentReg) {
      crAgentReg.textContent = state.registryWriteEnabled
        ? "Agent registration: Enabled on this service"
        : "Agent registration: Private only";
    }
    const codexAgent = (state.agents || []).find((agent) => agent.id === "codex_cli");
    const codexReady = !!(codexAgent && codexAgent.runnable);
    const codexChecked = codexAgent && codexAgent.last_checked_at
      ? ` · ${formatHistoryTimestamp(codexAgent.last_checked_at)}`
      : state.agentStatusLastChecked
        ? ` · ${formatHistoryTimestamp(state.agentStatusLastChecked)}`
        : "";
    if (inspectorCaptain) {
      inspectorCaptain.textContent = `Captain — ${deck.configured ? "Ready" : "Not configured"}`;
    }
    if (inspectorCodex) {
      inspectorCodex.textContent = `Codex CLI — ${codexReady ? "Ready" : "Disabled"}${codexChecked}`;
    }
    if (inspectorJules) {
      const julesChecked = (state.agents || []).find((agent) => agent.adapter === "jules_remote" && agent.user_created);
      const suffix = julesChecked && julesChecked.last_checked_at ? ` · ${formatHistoryTimestamp(julesChecked.last_checked_at)}` : "";
      inspectorJules.textContent = `Jules Remote — ${julesInspectorStatus()}${suffix}`;
    }
    if (useCodexDirectly) useCodexDirectly.style.display = runnerActive ? "" : "none";
    if (inspectorViewCodex) inspectorViewCodex.style.display = runnerActive ? "" : "none";
    if (inspectorNextMove) {
      if (!runnerActive) {
        inspectorNextMove.textContent = "Private runner is unavailable on this service.";
      } else if (!deck.configured) {
        inspectorNextMove.textContent = "Configure Captain before planning work.";
      } else {
        inspectorNextMove.textContent = "Create a plan, then dispatch the first bounded step to Codex.";
      }
    }
    updateRunsEvidenceActions();
  }

  function setActiveSection(sectionId) {
    state.activeSection = sectionId || "mission";
    document.querySelectorAll(".workspace-section").forEach((section) => {
      section.classList.toggle("active", section.dataset.section === state.activeSection);
    });
    document.querySelectorAll(".nav-item").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.section === state.activeSection);
    });
    const inspector = document.getElementById("operator-inspector");
    const showInspector = state.activeSection === "mission" || state.activeSection === "agents";
    if (inspector) inspector.style.display = showInspector ? "" : "none";
    const stage = document.querySelector(".warden-stage");
    if (stage) stage.classList.toggle("inspector-visible", showInspector);
    const titles = {
      mission: "Control Room",
      tasks: "Missions",
      agents: "Agents",
      runs: "Runs",
      evidence: "Evidence",
      "proof-gates": "Proof Gates",
      "runner-sessions": "Runner Sessions",
      settings: "Settings",
    };
    const topTitle = document.getElementById("topbar-page-title");
    if (topTitle) topTitle.textContent = titles[state.activeSection] || "Warden";
    if (window.WardenControlRoom && window.WardenControlRoom.onSectionChange) {
      window.WardenControlRoom.onSectionChange(state.activeSection);
    }
    if (state.activeSection === "mission") {
      Promise.all([loadActiveCaptainPlan(), loadMissionWorklog()]).catch((e) => console.error(e));
      if (window.WardenControlRoom && window.WardenControlRoom.isInitialized && window.WardenControlRoom.isInitialized() && window.WardenControlRoom.refresh) {
        window.WardenControlRoom.refresh({ quiet: true }).catch((e) => console.error(e));
      }
    } else if (state.activeSection === "runs") {
      loadRecentRuns().catch((e) => console.error(e));
    } else if (state.activeSection === "evidence") {
      loadRecentEvidence().catch((e) => console.error(e));
    }
  }

  function registeredAgentCardCopy(agent) {
    if (agent.adapter === "jules_remote") {
      const connected = agent.connection_status === "connected" && agent.status === "ready";
      return {
        pillLabel: connected ? "CONNECTED" : "SETUP NEEDED",
        pillClass: connected ? "status-connected" : "status-coming",
        body: "Connected for planning and status. Remote execution comes next.",
      };
    }
    const status = agentStatusLabel(agent);
    return {
      pillLabel: status === "connected" ? "Connected" : "Coming next",
      pillClass: status === "connected" ? "status-connected" : "status-coming",
      body: agent.description || "",
    };
  }

  function captainAgentOptionLabel(agent) {
    if (!agent) return "Unknown";
    if (agent.runnable || agent.id === "codex_cli") {
      return `${agent.name || agent.id} — Ready`;
    }
    if (agent.adapter === "jules_remote") {
      const connected = agent.connection_status === "connected";
      return `${agent.name || agent.id} — ${connected ? "Connected, execution coming next" : "Setup incomplete"}`;
    }
    return `${agent.name || agent.id} — Not runnable`;
  }

  function renderRegisteredAgentCards() {
    const container = document.getElementById("connected-agent-cards");
    const group = document.getElementById("agent-group-connected");
    if (!container) return;
    const registered = (state.agents || []).filter((agent) => agent.user_created);
    if (!registered.length) {
      container.innerHTML = "";
      if (group) group.style.display = "none";
      return;
    }
    if (group) group.style.display = "";
    container.innerHTML = registered.map((agent) => {
      const copy = registeredAgentCardCopy(agent);
      const runnable = !!agent.runnable;
      const showEdit = agent.adapter === "jules_remote";
      return `
        <div class="agent-card registered-agent-card" data-agent-id="${escapeHtml(agent.id)}">
          <div class="agent-card-top">
            <h3 class="agent-card-title">${escapeHtml(agent.name || agent.id)}</h3>
            <span class="status-pill ${copy.pillClass}">${escapeHtml(copy.pillLabel)}</span>
          </div>
          <p class="agent-card-copy">${escapeHtml(copy.body)}</p>
          <div class="agent-card-actions">
            ${agent.adapter === "jules_remote" ? `<a class="btn view-agent-link" href="${JULES_VIEW_URL}" target="_blank" rel="noopener noreferrer" title="Open Jules remote agent workspace" aria-label="View Agent — open Jules remote agent workspace" data-testid="view-agent-jules">View Agent</a>` : ""}
            ${runnable ? `<button class="btn" type="button" data-use-agent-id="${escapeHtml(agent.id)}">Use Agent</button>` : ""}
            ${showEdit ? `<button class="btn" type="button" data-edit-agent-id="${escapeHtml(agent.id)}">Edit Config</button>` : ""}
            <button class="btn bad" type="button" data-remove-agent-id="${escapeHtml(agent.id)}">Remove</button>
          </div>
        </div>
      `;
    }).join("");
    container.querySelectorAll("[data-remove-agent-id]").forEach((button) => {
      button.addEventListener("click", () => {
        const agentId = button.getAttribute("data-remove-agent-id");
        if (agentId) removeRegisteredAgent(agentId).catch((e) => console.error(e));
      });
    });
    container.querySelectorAll("[data-edit-agent-id]").forEach((button) => {
      button.addEventListener("click", () => {
        const agentId = button.getAttribute("data-edit-agent-id");
        if (agentId) openEditAgentModal(agentId).catch((e) => console.error(e));
      });
    });
    container.querySelectorAll("[data-use-agent-id]").forEach((button) => {
      button.addEventListener("click", () => openUseAgentModal());
    });
    renderSettingsPanel();
  }

  function populateCaptainAgents() {
    const sel = document.getElementById("captain-agent-select");
    if (!sel) return;
    const agents = state.agents || [];
    sel.innerHTML = "";
    agents.forEach((agent) => {
      const opt = document.createElement("option");
      opt.value = agent.id;
      opt.textContent = captainAgentOptionLabel(agent);
      opt.dataset.runnable = agent.runnable ? "1" : "0";
      sel.appendChild(opt);
    });
    if (agents.length) {
      const preferred = agents.find((agent) => agent.id === state.captainDeck.laneId) || agents.find((agent) => agent.runnable) || agents[0];
      sel.value = preferred.id;
      state.captainDeck.laneId = preferred.id;
    }
  }

  function resetAddAgentFormFields({ keepName = false, keepRepo = false } = {}) {
    const nameEl = document.getElementById("add-agent-name");
    const keyEl = document.getElementById("add-agent-api-key");
    const branchEl = document.getElementById("add-agent-branch");
    const approvalEl = document.getElementById("add-agent-require-plan-approval");
    const unverifiedEl = document.getElementById("add-agent-allow-unverified");
    if (nameEl && !keepName) nameEl.value = "";
    if (keyEl) keyEl.value = "";
    if (branchEl && !keepRepo) branchEl.value = "";
    if (approvalEl) approvalEl.checked = true;
    if (unverifiedEl) unverifiedEl.checked = false;
    state.addAgent.lastTestStatus = "";
    const testStatus = document.getElementById("add-agent-test-status");
    if (testStatus) {
      testStatus.style.display = "none";
      testStatus.textContent = "";
    }
  }

  function renderAddAgentTemplateList() {
    const list = document.getElementById("add-agent-template-list");
    if (!list) return;
    const templates = state.agentTemplates || [];
    list.innerHTML = templates.map((template) => {
      const suffix = template.builtin ? " — Installed" : (template.registerable ? " — Configure" : " — Coming later");
      const disabled = !template.registerable && !template.builtin;
      return `
        <button
          class="btn ${template.registerable ? "primary" : ""}"
          type="button"
          data-template-adapter="${escapeHtml(template.adapter)}"
          data-template-registerable="${template.registerable ? "1" : "0"}"
          data-template-builtin="${template.builtin ? "1" : "0"}"
          ${disabled ? "disabled" : ""}
          style="justify-content:flex-start; text-align:left; width:100%;"
        >
          ${escapeHtml(template.label || template.adapter)}${escapeHtml(suffix)}
        </button>
      `;
    }).join("");
    list.querySelectorAll("[data-template-adapter]").forEach((button) => {
      button.addEventListener("click", () => {
        const adapter = button.getAttribute("data-template-adapter") || "";
        const registerable = button.getAttribute("data-template-registerable") === "1";
        const builtin = button.getAttribute("data-template-builtin") === "1";
        if (builtin) {
          const err = document.getElementById("add-agent-error");
          if (err) {
            err.textContent = "Codex CLI is built-in and already installed.";
            err.style.display = "block";
          }
          return;
        }
        if (!registerable) return;
        state.addAgent.templateAdapter = adapter;
        showAddAgentConfigStep();
      });
    });
  }

  function showAddAgentChooseStep() {
    state.addAgent.step = "choose";
    const choose = document.getElementById("add-agent-step-choose");
    const config = document.getElementById("add-agent-step-config");
    const backBtn = document.getElementById("add-agent-back");
    const testBtn = document.getElementById("add-agent-test");
    const saveBtn = document.getElementById("add-agent-save");
    const title = document.getElementById("add-agent-title");
    if (choose) choose.style.display = "block";
    if (config) config.style.display = "none";
    if (backBtn) backBtn.style.display = "none";
    if (testBtn) testBtn.style.display = "none";
    if (saveBtn) saveBtn.style.display = "none";
    if (title) title.textContent = state.addAgent.mode === "edit" ? "Edit Agent Config" : "Add Agent";
    renderAddAgentTemplateList();
    updateAddAgentActions();
  }

  function showAddAgentConfigStep() {
    state.addAgent.step = "config";
    const choose = document.getElementById("add-agent-step-choose");
    const config = document.getElementById("add-agent-step-config");
    const backBtn = document.getElementById("add-agent-back");
    const testBtn = document.getElementById("add-agent-test");
    const saveBtn = document.getElementById("add-agent-save");
    const title = document.getElementById("add-agent-title");
    if (choose) choose.style.display = "none";
    if (config) config.style.display = "block";
    if (backBtn) backBtn.style.display = state.addAgent.mode === "create" ? "inline-flex" : "none";
    if (testBtn) testBtn.style.display = "inline-flex";
    if (saveBtn) saveBtn.style.display = "inline-flex";
    if (title) title.textContent = state.addAgent.templateAdapter === "jules_remote" ? "Configure Jules Remote" : "Configure Agent";
    updateAddAgentActions();
  }

  function updateAddAgentActions() {
    const saveBtn = document.getElementById("add-agent-save");
    const testBtn = document.getElementById("add-agent-test");
    const allowUnverified = document.getElementById("add-agent-allow-unverified");
    const keyEl = document.getElementById("add-agent-api-key");
    const editingMetadataOnly = state.addAgent.mode === "edit" && !(keyEl && keyEl.value ? keyEl.value : "").trim();
    const canSave = editingMetadataOnly
      || state.addAgent.lastTestStatus === "connected"
      || (allowUnverified && allowUnverified.checked && ["not_verified", "error"].includes(state.addAgent.lastTestStatus));
    if (saveBtn) {
      saveBtn.disabled = state.addAgent.step !== "config"
        || !state.registryWriteEnabled
        || !!state.addAgent.saving
        || !!state.addAgent.testing
        || !canSave;
    }
    if (testBtn) {
      testBtn.disabled = state.addAgent.step !== "config"
        || !state.registryWriteEnabled
        || !!state.addAgent.saving
        || !!state.addAgent.testing;
      testBtn.textContent = state.addAgent.testing ? "Testing..." : "Test Connection";
    }
    if (saveBtn) saveBtn.textContent = state.addAgent.saving ? "Saving..." : "Save Agent";
  }

  async function populateAddAgentRepos() {
    const sel = document.getElementById("add-agent-repo");
    if (!sel) return;
    sel.innerHTML = '<option value="">No default repo</option>';
    const repos = state.repos.length ? state.repos : [];
    if (!repos.length) {
      try {
        const data = await requestJson(`${MCH}/repos`);
        state.repos = data.repos || [];
      } catch (e) {
        state.repos = [];
      }
    }
    (state.repos || []).forEach((repo) => {
      const opt = document.createElement("option");
      opt.value = repo.repo_id || repo.path;
      opt.textContent = repo.label || repo.repo_id || repo.path;
      sel.appendChild(opt);
    });
  }

  function collectJulesConfigPayload() {
    const nameEl = document.getElementById("add-agent-name");
    const keyEl = document.getElementById("add-agent-api-key");
    const repoEl = document.getElementById("add-agent-repo");
    const branchEl = document.getElementById("add-agent-branch");
    const approvalEl = document.getElementById("add-agent-require-plan-approval");
    const unverifiedEl = document.getElementById("add-agent-allow-unverified");
    return {
      name: (nameEl && nameEl.value ? nameEl.value : "").trim(),
      api_key: (keyEl && keyEl.value ? keyEl.value : "").trim(),
      default_repo_id: repoEl && repoEl.value ? repoEl.value : null,
      default_branch: (branchEl && branchEl.value ? branchEl.value : "").trim() || null,
      require_plan_approval: !!(approvalEl && approvalEl.checked),
      allow_unverified: !!(unverifiedEl && unverifiedEl.checked),
    };
  }

  async function openAddAgentModal() {
    const modal = document.getElementById("add-agent-modal");
    if (!modal) return;
    state.addAgent.mode = "create";
    state.addAgent.editingAgentId = "";
    state.addAgent.error = "";
    state.addAgent.saving = false;
    state.addAgent.testing = false;
    state.addAgent.templateAdapter = "";
    resetAddAgentFormFields();
    modal.style.display = "flex";
    await Promise.all([loadAgentTemplates(), loadAgents(), populateAddAgentRepos()]);
    const err = document.getElementById("add-agent-error");
    if (err) {
      err.style.display = "none";
      err.textContent = "";
    }
    if (!state.registryWriteEnabled && err) {
      err.textContent = "Agent configuration is available only on the private runner service.";
      err.style.display = "block";
    }
    showAddAgentChooseStep();
  }

  async function openEditAgentModal(agentId) {
    const agent = (state.agents || []).find((item) => item.id === agentId);
    if (!agent) return;
    const modal = document.getElementById("add-agent-modal");
    if (!modal) return;
    state.addAgent.mode = "edit";
    state.addAgent.editingAgentId = agentId;
    state.addAgent.templateAdapter = agent.adapter || "jules_remote";
    state.addAgent.error = "";
    state.addAgent.saving = false;
    state.addAgent.testing = false;
    state.addAgent.lastTestStatus = "";
    resetAddAgentFormFields({ keepName: true, keepRepo: true });
    const nameEl = document.getElementById("add-agent-name");
    const branchEl = document.getElementById("add-agent-branch");
    const approvalEl = document.getElementById("add-agent-require-plan-approval");
    if (nameEl) nameEl.value = agent.name || "";
    if (branchEl) branchEl.value = agent.default_branch || "";
    if (approvalEl) approvalEl.checked = agent.require_plan_approval !== false;
    await populateAddAgentRepos();
    const repoEl = document.getElementById("add-agent-repo");
    if (repoEl && agent.default_repo_id) repoEl.value = agent.default_repo_id;
    modal.style.display = "flex";
    const err = document.getElementById("add-agent-error");
    if (err) {
      err.style.display = "none";
      err.textContent = "";
    }
    showAddAgentConfigStep();
  }

  function closeAddAgentModal() {
    const modal = document.getElementById("add-agent-modal");
    if (modal) modal.style.display = "none";
    resetAddAgentFormFields();
    state.addAgent.step = "choose";
    state.addAgent.mode = "create";
    state.addAgent.editingAgentId = "";
    state.addAgent.templateAdapter = "";
    state.addAgent.lastTestStatus = "";
  }

  async function testAddAgentConnection() {
    const err = document.getElementById("add-agent-error");
    const testStatus = document.getElementById("add-agent-test-status");
    const payload = collectJulesConfigPayload();
    if (!payload.api_key) {
      if (err) {
        err.textContent = "Enter a Jules API key before testing the connection.";
        err.style.display = "block";
      }
      return;
    }
    if (!state.registryWriteEnabled) {
      if (err) {
        err.textContent = "Agent configuration is available only on the private runner service.";
        err.style.display = "block";
      }
      return;
    }
    state.addAgent.testing = true;
    if (err) err.style.display = "none";
    updateAddAgentActions();
    try {
      const result = await requestJson(`${MCH}/agents/test-config`, {
        method: "POST",
        body: {
          adapter: "jules_remote",
          api_key: payload.api_key,
          default_repo_id: payload.default_repo_id,
          default_branch: payload.default_branch,
        },
      });
      state.addAgent.lastTestStatus = result.status || "";
      if (testStatus) {
        testStatus.textContent = result.message || `Connection status: ${result.status || "unknown"}`;
        testStatus.style.display = "block";
        testStatus.style.color = result.status === "connected"
          ? "var(--good, #63db9d)"
          : (result.status === "invalid_key" ? "var(--bad, #ff7e91)" : "var(--warn, #f0c66a)");
      }
    } catch (e) {
      state.addAgent.lastTestStatus = "";
      if (err) {
        err.textContent = e.message || String(e);
        err.style.display = "block";
      }
    } finally {
      state.addAgent.testing = false;
      updateAddAgentActions();
    }
  }

  async function saveAddAgent() {
    const err = document.getElementById("add-agent-error");
    const payload = collectJulesConfigPayload();
    const template = (state.agentTemplates || []).find((item) => item.adapter === state.addAgent.templateAdapter);
    if (!payload.name) {
      if (err) {
        err.textContent = "Display name is required.";
        err.style.display = "block";
      }
      return;
    }
    if (!state.registryWriteEnabled) {
      if (err) {
        err.textContent = "Agent configuration is available only on the private runner service.";
        err.style.display = "block";
      }
      return;
    }
    if (state.addAgent.mode === "edit" && state.addAgent.editingAgentId && !payload.api_key) {
      state.addAgent.saving = true;
      updateAddAgentActions();
      try {
        await requestJson(`${MCH}/agents/${encodeURIComponent(state.addAgent.editingAgentId)}/config`, {
          method: "PATCH",
          body: {
            default_repo_id: payload.default_repo_id,
            default_branch: payload.default_branch,
            require_plan_approval: payload.require_plan_approval,
          },
        });
        resetAddAgentFormFields();
        if (err) err.style.display = "none";
        await loadAgents();
        closeAddAgentModal();
      } catch (e) {
        if (err) {
          err.textContent = e.message || String(e);
          err.style.display = "block";
        }
      } finally {
        state.addAgent.saving = false;
        updateAddAgentActions();
      }
      return;
    }
    if (!payload.api_key) {
      if (err) {
        err.textContent = "Jules API key is required to save this agent.";
        err.style.display = "block";
      }
      return;
    }
    const canSave = state.addAgent.lastTestStatus === "connected"
      || (payload.allow_unverified && ["not_verified", "error"].includes(state.addAgent.lastTestStatus));
    if (!canSave) {
      if (err) {
        err.textContent = "Test the Jules connection first, or allow saving as an unverified profile.";
        err.style.display = "block";
      }
      return;
    }
    state.addAgent.saving = true;
    updateAddAgentActions();
    try {
      if (state.addAgent.mode === "edit" && state.addAgent.editingAgentId) {
        await requestJson(`${MCH}/agents/${encodeURIComponent(state.addAgent.editingAgentId)}/config`, {
          method: "PATCH",
          body: {
            api_key: payload.api_key,
            default_repo_id: payload.default_repo_id,
            default_branch: payload.default_branch,
            require_plan_approval: payload.require_plan_approval,
            allow_unverified: payload.allow_unverified,
          },
        });
      } else {
        await requestJson(`${MCH}/agents`, {
          method: "POST",
          body: {
            name: payload.name,
            kind: template ? template.kind : "remote",
            adapter: "jules_remote",
            default_repo_id: payload.default_repo_id,
            default_branch: payload.default_branch,
            require_plan_approval: payload.require_plan_approval,
            enabled: true,
            description: template ? template.description : "",
            api_key: payload.api_key,
            allow_unverified: payload.allow_unverified,
          },
        });
      }
      resetAddAgentFormFields();
      if (err) err.style.display = "none";
      await loadAgents();
      closeAddAgentModal();
    } catch (e) {
      if (err) {
        err.textContent = e.message || String(e);
        err.style.display = "block";
      }
    } finally {
      state.addAgent.saving = false;
      updateAddAgentActions();
    }
  }

  async function removeRegisteredAgent(agentId) {
    if (!state.registryWriteEnabled) {
      alert("Agent registration is available only on the private runner service.");
      return;
    }
    try {
      await requestJson(`${MCH}/agents/${encodeURIComponent(agentId)}`, { method: "DELETE" });
      await loadAgents();
    } catch (e) {
      alert("Remove failed: " + (e.message || e));
    }
  }

  // Load for library card status (from lanes + health + registry)
  async function loadLibraryStatus() {
    try {
      const [lanesData, health] = await Promise.all([
        requestJson(`${MCH}/agent-lanes`),
        requestJson(`${MCH}/health`),
      ]);
      state.lanes = lanesData.lanes || [];
      state.health = health || {};
      await loadAgents();
      const codex = (state.agents || []).find((agent) => agent.id === "codex_cli")
        || state.lanes.find((l) => l.lane_id === "codex_cli")
        || {};
      const installed = !!codex.installed || codex.status === "ready" || codex.status === "disabled";
      const tmuxF = !!state.health.tmux_runner_enabled;
      const codexF = !!state.health.codex_runner_enabled;
      if (codex.status === "ready" || (installed && tmuxF && codexF)) {
        setCodexStatusPill({ ready: true, label: "READY" });
      } else if (installed) {
        setCodexStatusPill({ disabled: true, label: "DISABLED" });
      } else {
        setCodexStatusPill({ disabled: true, label: "DISABLED" });
      }
      renderCodexCapabilityChips(codex);
      const statusLine = document.getElementById("codex-status-line");
      if (statusLine) {
        const checkedAt = codex.last_checked_at || state.agentStatusLastChecked;
        if (checkedAt) {
          statusLine.style.display = "";
          statusLine.textContent = `Last checked ${formatHistoryTimestamp(checkedAt)}`;
        } else {
          statusLine.style.display = "none";
          statusLine.textContent = "";
        }
      }
      renderSettingsPanel();
    } catch (e) {
      setCodexStatusPill({ disabled: true, label: "Disabled" });
      renderSettingsPanel();
    }
  }

  // Populate repo select in use-agent modal (from /repos)
  async function populateModalRepos() {
    const sel = document.getElementById("modal-repo-select");
    if (!sel) return;
    sel.innerHTML = '<option value="">Loading repos...</option>';
    try {
      const data = await requestJson(`${MCH}/repos`);
      const repos = data.repos || [];
      sel.innerHTML = "";
      repos.forEach((r) => {
        const opt = document.createElement("option");
        opt.value = r.path || r.repo_id; // path for session, id for runner
        opt.dataset.repoId = r.repo_id;
        opt.textContent = r.label || r.path;
        sel.appendChild(opt);
      });
      if (repos.length) sel.value = repos[0].path || repos[0].repo_id;
    } catch (e) {
      sel.innerHTML = '<option value="/root/mcharness-public-export">mcharness-public-export (fallback)</option>';
    }
  }

  // Use Agent modal open
  function openUseAgentModal() {
    const modal = document.getElementById("use-agent-modal");
    if (!modal) return;
    modal.style.display = "flex";
    populateModalRepos();
    // clear fields
    const t = document.getElementById("modal-task-title");
    const p = document.getElementById("modal-prompt");
    if (t) t.value = "";
    if (p) p.value = "";
    const note = document.getElementById("deploy-disabled-note");
    if (note) note.style.display = "none";
  }

  function closeUseAgentModal() {
    const modal = document.getElementById("use-agent-modal");
    if (modal) modal.style.display = "none";
  }

  function closeSetupModals() {
    closeUseAgentModal();
    closeCaptainDeckModal();
    closeAddAgentModal();
  }

  async function deployRunnerPrompt({ title, prompt, repoPath, repoId, planId = null, closeCurrentModal = null, noteId = "deploy-disabled-note" }) {
    const note = noteId ? document.getElementById(noteId) : null;
    const health = state.health || {};
    const canRunReal = !!(health.tmux_runner_enabled && health.codex_runner_enabled);
    if (!canRunReal && note) {
      note.textContent = "Codex runner is disabled. Start private runner mode (8125 + both MCHARNESS_TMUX_RUNNER_ENABLED=true and MCHARNESS_CODEX_RUNNER_ENABLED=true) to use Deploy Prompt for real Codex.";
      note.style.display = "block";
    }

    try {
      const sess = await requestJson(`${MCH}/sessions`, {
        method: "POST",
        body: {
          title,
          objective: title,
          plan_instruction: prompt,
          repo_path: repoPath,
          agent_lane: "codex_cli",
        },
      });
      const sid = sess.session_id || sess.id;
      state.selectedThreadId = sid;
      updateRunsEvidenceActions();

      const qres = await requestJson(`${MCH}/sessions/${encodeURIComponent(sid)}/queue`, {
        method: "POST",
        body: { title: "Task prompt", prompt },
      });
      const qid = qres.queue_item_id || qres.id;

      try {
        await requestJson(`${MCH}/sessions/${encodeURIComponent(sid)}/prompt-export`, {
          method: "POST",
          body: { queue_item_id: qid, mark_sent: false },
        });
      } catch (e) { /* non fatal */ }

      const runnerState = await requestJson(`${MCH}/sessions/${encodeURIComponent(sid)}/runner/start`, {
        method: "POST",
        body: {
          lane_id: "codex_cli",
          repo_id: repoId,
          queue_item_id: qid,
          title,
          prompt,
          plan_id: planId,
          agent_id: "codex_cli",
          created_by: planId ? "captain_deck" : "use_agent",
        },
      });
      state.activeWardenRunId = (runnerState && (runnerState.runner_id || (runnerState.warden_run && runnerState.warden_run.run_id))) || "";
      await Promise.all([loadRecentRuns(), loadRecentEvidence(), loadMissionWorklog()]);

      if (typeof closeCurrentModal === "function") closeCurrentModal();
      closeSetupModals();
      openLiveCLIMonitor();

      setTimeout(async () => {
        try {
          const result = await requestJson(`${MCH}/sessions/${encodeURIComponent(sid)}/runner/send-prompt`, {
            method: "POST",
            body: { prompt },
          });
          state.promptSubmittedAt = Date.now();
          if (result && result.status) {
            state.health.runner_status = result.status;
          }
          setQuickReplyStatus("Prompt sent to Codex.");
          if (typeof refreshLiveMonitor === "function") await refreshLiveMonitor();
        } catch (e) {
          if (typeof refreshLiveMonitor === "function") await refreshLiveMonitor();
        }
      }, 10000);

      return sid;
    } catch (err) {
      if (typeof closeCurrentModal === "function") closeCurrentModal();
      alert("Deploy failed: " + (err.message || err));
      if (state.selectedThreadId) openLiveCLIMonitor();
      throw err;
    }
  }

  // Deploy Prompt flow (create, queue, export, start, open monitor, delayed send)
  async function deployPrompt() {
    const repoSel = document.getElementById("modal-repo-select");
    const titleEl = document.getElementById("modal-task-title");
    const promptEl = document.getElementById("modal-prompt");
    if (!repoSel || !titleEl || !promptEl) return;

    const repoPath = repoSel.value || "/root/mcharness-public-export";
    const repoId = (repoSel.selectedOptions[0] && repoSel.selectedOptions[0].dataset.repoId) || "mcharness-public-export";
    const title = (titleEl.value || "Untitled task").trim();
    const prompt = (promptEl.value || "Perform the task described.").trim();

    if (!title || !prompt) {
      alert("Title and prompt are required.");
      return;
    }

    await deployRunnerPrompt({
      title,
      prompt,
      repoPath,
      repoId,
      closeCurrentModal: closeUseAgentModal,
    });
  }

  // Live CLI Monitor (adapted from previous implementation, read-only, polls while open)
  let liveMonitorInterval = null;
  let liveAutoRefresh = true;

  function openLiveCLIMonitor() {
    closeSetupModals();
    const modal = document.getElementById("live-cli-modal");
    if (!modal) return;
    modal.style.display = "flex";
    state.promptSubmittedAt = state.promptSubmittedAt || 0;
    state.liveAutoScroll = true;
    state.lastMonitorTranscriptText = "";
    setQuickReplyStatus("");
    updateLiveMonitorChrome();
    refreshLiveMonitor();
    if (liveAutoRefresh) startMonitorPolling();
  }

  function closeLiveCLIMonitor() {
    const modal = document.getElementById("live-cli-modal");
    if (modal) modal.style.display = "none";
    setQuickReplyStatus("");
    stopMonitorPolling();
  }

  function startMonitorPolling() {
    stopMonitorPolling();
    liveMonitorInterval = setInterval(() => {
      const modal = document.getElementById("live-cli-modal");
      if (modal && modal.style.display !== "none" && liveAutoRefresh) {
        refreshLiveMonitor();
      }
    }, 1500);
  }

  function stopMonitorPolling() {
    if (liveMonitorInterval) {
      clearInterval(liveMonitorInterval);
      liveMonitorInterval = null;
    }
  }

  async function refreshLiveMonitor() {
    const sid = state.selectedThreadId;
    if (!sid) {
      const empty = document.getElementById("modal-empty");
      if (empty) empty.style.display = "";
      return;
    }
    try {
      const [status, trans] = await Promise.all([
        requestJson(`${MCH}/sessions/${encodeURIComponent(sid)}/runner/status`),
        requestJson(`${MCH}/sessions/${encodeURIComponent(sid)}/runner/transcript`),
      ]);
      // update UI elements (ids from the modal in html)
      const laneEl = document.getElementById("modal-lane-name");
      if (laneEl) laneEl.textContent = "";
      const infoEl = document.getElementById("modal-info");
      const statusText = status.status || "n/a";
      const txt = (trans && trans.transcript) ? trans.transcript : (status.transcript || "");
      const hasTranscriptOutput = !!String(txt || "").trim();
      const monitorStatusLabel = (() => {
        if (statusText === "failed") return "Failed";
        if (statusText === "exited") return "Finished";
        if (statusText === "stopped") return "Stopped";
        if (statusText === "starting") return "Starting Codex...";
        if (statusText === "waiting_for_codex") return hasTranscriptOutput ? "Running" : "Opening Codex...";
        if (statusText === "prompt_sent") return "Running";
        if (statusText === "awaiting_response") return "Running";
        if (statusText === "running") return "Running";
        return statusText;
      })();
      const sessionName = status.tmux_session_name || "n/a";
      if (infoEl) {
        infoEl.innerHTML = `
          <div><strong>Repo:</strong> ${status.repo_id || "n/a"}</div>
          <div><strong>Status:</strong> ${monitorStatusLabel}</div>
          <div><strong>Session:</strong> ${sessionName}</div>
        `;
      }
      const pre = document.getElementById("modal-transcript");
      let displayTxt = txt || "Waiting for CLI output...";
      if (pre) {
        const shouldStick = state.liveAutoScroll && isModalTranscriptNearBottom(pre);
        const previousScrollTop = pre.scrollTop;
        pre.textContent = displayTxt;
        if (shouldStick) {
          scrollModalTranscriptToBottom();
        } else {
          pre.scrollTop = previousScrollTop;
        }
        // warning if only exit code visible (means launch didn't keep interactive or capture missed TUI)
        if (displayTxt.trim() === "MCH_EXIT_CODE:0" || (displayTxt.trim().length < 30 && displayTxt.includes("EXIT"))) {
          pre.textContent = displayTxt + "\n\n[Warning] Runner exited before producing visible CLI output. Check flags, codex auth, or tmux attach manually.";
          if (shouldStick) scrollModalTranscriptToBottom();
        }
      }
      const elapsed = state.promptSubmittedAt ? Date.now() - state.promptSubmittedAt : 0;
      const transcriptTrimmed = String(txt || "").trim();
      if (elapsed > 10000 && statusText !== "running" && !transcriptTrimmed) {
        setQuickReplyStatus("Transcript is not updating yet. Use the buttons below if Codex is waiting for input.");
      }
      state.lastMonitorTranscriptText = transcriptTrimmed;
      const ts = document.getElementById("modal-timestamp");
      if (ts) ts.textContent = `Last refreshed: ${new Date().toLocaleTimeString()}`;

      // store for buttons
      const modal = document.getElementById("live-cli-modal");
      if (modal) {
        modal.dataset.attach = status.attach_command || (status.tmux_session_name ? `tmux attach -t ${status.tmux_session_name}` : "");
        modal.dataset.transcript = txt;
      }

      // hide states
      const e = document.getElementById("modal-empty");
      const d = document.getElementById("modal-disabled");
      if (e) e.style.display = "none";
      if (d) d.style.display = "none";
    } catch (e) {
      const empty = document.getElementById("modal-empty");
      if (empty) {
        empty.style.display = "";
        empty.textContent = "No active runner or error fetching status. (Runner disabled in public mode?)";
      }
    }
  }

  async function sendQuickReply(key) {
    const sid = state.selectedThreadId;
    if (!sid) {
      setQuickReplyStatus("Failed: no active runner", true);
      return;
    }
    if (key === "Submit / Continue") {
      setQuickReplyStatus("Sending: Submit / Continue");
    } else {
      setQuickReplyStatus(`Sending: ${key}`);
    }
    try {
      const result = await requestJson(`${MCH}/sessions/${encodeURIComponent(sid)}/runner/send-key`, {
        method: "POST",
        body: { key },
      });
      if (key === "Submit / Continue") {
        setQuickReplyStatus((result && result.status_note) || "Prompt sent to Codex.");
      } else {
        setQuickReplyStatus(`Sent: ${key}`);
      }
      const pre = document.getElementById("modal-transcript");
      if (pre && result && result.transcript_excerpt) {
        const shouldStick = state.liveAutoScroll && isModalTranscriptNearBottom(pre);
        pre.textContent = result.transcript_excerpt;
        if (shouldStick) scrollModalTranscriptToBottom();
      }
      await refreshLiveMonitor();
    } catch (e) {
      setQuickReplyStatus(`Failed: ${e.message || e}`, true);
    }
  }

  function wireDevelopPlanButtons() {
    const openCaptain = () => openCaptainDeckModal().catch((e) => console.error(e));
    document.querySelectorAll("[data-action='develop-plan']").forEach((btn) => {
      btn.addEventListener("click", openCaptain);
    });
  }

  function wireWorkspaceNav() {
    document.querySelectorAll(".nav-item").forEach((btn) => {
      btn.addEventListener("click", () => {
        const section = btn.dataset.section;
        if (section) setActiveSection(section);
      });
    });
    const configureCaptain = document.getElementById("configure-captain-btn");
    if (configureCaptain) {
      configureCaptain.addEventListener("click", () => {
        openCaptainDeckModal().catch((e) => console.error(e));
      });
    }
    const runDetailClose = document.getElementById("run-detail-close");
    if (runDetailClose) runDetailClose.addEventListener("click", closeRunDetailModal);
    document.querySelectorAll("[data-evidence-filter]").forEach((button) => {
      button.addEventListener("click", () => {
        state.evidenceTypeFilter = button.getAttribute("data-evidence-filter") || "all";
        renderEvidencePanel();
      });
    });
    document.querySelectorAll("[data-timeline-filter]").forEach((button) => {
      button.addEventListener("click", () => {
        state.missionTimelineFilter = button.getAttribute("data-timeline-filter") || "all";
        renderMissionWorklog();
      });
    });
    document.querySelectorAll("[data-section-jump]").forEach((button) => {
      button.addEventListener("click", () => {
        const section = button.getAttribute("data-section-jump");
        if (section) setActiveSection(section);
      });
    });
    const evidenceDetailClose = document.getElementById("evidence-detail-close");
    if (evidenceDetailClose) evidenceDetailClose.addEventListener("click", closeEvidenceDetailModal);
    const runDetailModal = document.getElementById("run-detail-modal");
    if (runDetailModal) runDetailModal.addEventListener("click", (e) => { if (e.target === runDetailModal) closeRunDetailModal(); });
    const evidenceDetailModal = document.getElementById("evidence-detail-modal");
    if (evidenceDetailModal) evidenceDetailModal.addEventListener("click", (e) => { if (e.target === evidenceDetailModal) closeEvidenceDetailModal(); });
    ["runs-open-monitor", "evidence-open-output"].forEach((id) => {
      const btn = document.getElementById(id);
      if (btn) btn.addEventListener("click", openLiveCLIMonitor);
    });
  }

  // Wire simple UI events
  function wireSimpleUI() {
    wireDevelopPlanButtons();
    wireWorkspaceNav();

    // Use Agent
    const useBtn = document.getElementById("use-codex-btn");
    if (useBtn) useBtn.addEventListener("click", openUseAgentModal);

    const useCodexDirectly = document.getElementById("use-codex-directly");
    if (useCodexDirectly) useCodexDirectly.addEventListener("click", openUseAgentModal);

    const inspectorViewCodex = document.getElementById("inspector-view-codex");
    if (inspectorViewCodex) inspectorViewCodex.addEventListener("click", openLiveCLIMonitor);

    const viewCodexBtn = document.getElementById("view-agent-codex-btn");
    if (viewCodexBtn) viewCodexBtn.addEventListener("click", openLiveCLIMonitor);

    const refreshAgentStatus = document.getElementById("refresh-agent-status");
    if (refreshAgentStatus) {
      refreshAgentStatus.addEventListener("click", () => {
        refreshAgentStatuses().catch((e) => console.error(e));
      });
    }
    const inspectorRefreshAgents = document.getElementById("inspector-refresh-agents");
    if (inspectorRefreshAgents) {
      inspectorRefreshAgents.addEventListener("click", () => {
        refreshAgentStatuses().catch((e) => console.error(e));
      });
    }

    const cancel = document.getElementById("cancel-use-agent");
    if (cancel) cancel.addEventListener("click", closeUseAgentModal);

    const deploy = document.getElementById("deploy-prompt-btn");
    if (deploy) deploy.addEventListener("click", () => {
      // run deploy (async but fire)
      deployPrompt().catch((e) => console.error(e));
    });

    const captainClose = document.getElementById("captain-close");
    if (captainClose) captainClose.addEventListener("click", closeCaptainDeckModal);
    const captainCreate = document.getElementById("captain-create-plan");
    if (captainCreate) captainCreate.addEventListener("click", () => {
      createCaptainPlan().catch((e) => console.error(e));
    });
    const captainDeploy = document.getElementById("captain-deploy-first");
    if (captainDeploy) captainDeploy.addEventListener("click", () => {
      deployCaptainFirstPrompt().catch((e) => console.error(e));
    });
    const captainCopy = document.getElementById("captain-copy-plan");
    if (captainCopy) captainCopy.addEventListener("click", () => {
      copyCaptainPlan().catch((e) => console.error(e));
    });
    const captainSetKey = document.getElementById("captain-set-key");
    if (captainSetKey) captainSetKey.addEventListener("click", () => {
      openCaptainKeyForm();
    });
    const captainSaveKey = document.getElementById("captain-save-key");
    if (captainSaveKey) captainSaveKey.addEventListener("click", () => {
      saveCaptainKey().catch((e) => console.error(e));
    });
    const captainCancelKey = document.getElementById("captain-cancel-key");
    if (captainCancelKey) captainCancelKey.addEventListener("click", () => {
      closeCaptainKeyForm();
    });
    const captainRemoveKey = document.getElementById("captain-remove-key");
    if (captainRemoveKey) captainRemoveKey.addEventListener("click", () => {
      removeCaptainKey().catch((e) => console.error(e));
    });
    const captainGoal = document.getElementById("captain-goal");
    if (captainGoal) captainGoal.addEventListener("input", () => {
      state.captainDeck.goal = captainGoal.value || "";
    });
    const captainOpenrouterModel = document.getElementById("captain-openrouter-model");
    if (captainOpenrouterModel) captainOpenrouterModel.addEventListener("input", () => {
      state.captainDeck.keyModel = captainOpenrouterModel.value || "openrouter/auto";
    });
    const captainRepo = document.getElementById("captain-repo-select");
    if (captainRepo) captainRepo.addEventListener("change", () => {
      const selected = captainRepo.selectedOptions[0];
      state.captainDeck.repoId = captainRepo.value;
      state.captainDeck.repoPath = (selected && selected.dataset.repoPath) || "";
    });
    const captainLane = document.getElementById("captain-agent-select");
    if (captainLane) captainLane.addEventListener("change", () => {
      state.captainDeck.laneId = captainLane.value || "codex_cli";
      renderCaptainDeck();
    });

    const addAgentBtn = document.getElementById("add-agent-btn");
    if (addAgentBtn) addAgentBtn.addEventListener("click", () => {
      openAddAgentModal().catch((e) => console.error(e));
    });
    const addAgentClose = document.getElementById("add-agent-close");
    if (addAgentClose) addAgentClose.addEventListener("click", closeAddAgentModal);
    const addAgentSave = document.getElementById("add-agent-save");
    if (addAgentSave) addAgentSave.addEventListener("click", () => {
      saveAddAgent().catch((e) => console.error(e));
    });
    const addAgentTest = document.getElementById("add-agent-test");
    if (addAgentTest) addAgentTest.addEventListener("click", () => {
      testAddAgentConnection().catch((e) => console.error(e));
    });
    const addAgentBack = document.getElementById("add-agent-back");
    if (addAgentBack) addAgentBack.addEventListener("click", () => {
      showAddAgentChooseStep();
    });
    const addAgentAllowUnverified = document.getElementById("add-agent-allow-unverified");
    if (addAgentAllowUnverified) addAgentAllowUnverified.addEventListener("change", updateAddAgentActions);
    const addAgentApiKey = document.getElementById("add-agent-api-key");
    if (addAgentApiKey) addAgentApiKey.addEventListener("input", () => {
      state.addAgent.lastTestStatus = "";
      updateAddAgentActions();
    });
    const addAgentModal = document.getElementById("add-agent-modal");
    if (addAgentModal) addAgentModal.addEventListener("click", (e) => {
      if (e.target === addAgentModal) closeAddAgentModal();
    });

    // Monitor buttons (if elements exist from the modal HTML)
    const mRefresh = document.getElementById("modal-refresh");
    if (mRefresh) mRefresh.addEventListener("click", refreshLiveMonitor);
    const mAuto = document.getElementById("modal-autorefresh");
    if (mAuto) mAuto.addEventListener("click", () => {
      liveAutoRefresh = !liveAutoRefresh;
      mAuto.textContent = `Auto-refresh: ${liveAutoRefresh ? "ON" : "OFF"}`;
      if (liveAutoRefresh) startMonitorPolling();
      else stopMonitorPolling();
    });
    const mJump = document.getElementById("modal-jump-latest");
    if (mJump) mJump.addEventListener("click", resumeLiveAutoScroll);
    const mExpand = document.getElementById("modal-expand");
    if (mExpand) mExpand.addEventListener("click", () => {
      state.liveMonitorExpanded = !state.liveMonitorExpanded;
      updateLiveMonitorChrome();
    });
    const mCopy = document.getElementById("modal-copy-attach");
    if (mCopy) mCopy.addEventListener("click", () => {
      const modal = document.getElementById("live-cli-modal");
      const cmd = modal ? modal.dataset.attach : "";
      if (cmd) navigator.clipboard.writeText(cmd).catch(() => prompt("Copy:", cmd));
    });
    const mSave = document.getElementById("modal-save-evidence");
    if (mSave) mSave.addEventListener("click", async () => {
      const sid = state.selectedThreadId;
      if (!sid) return;
      try {
        const result = await requestJson(`${MCH}/sessions/${encodeURIComponent(sid)}/runner/transcript-to-evidence`, { method: "POST" });
        if (result && result.warden_evidence && result.warden_evidence.evidence_id) {
          state.activeWardenRunId = result.warden_evidence.run_id || state.activeWardenRunId;
        }
        await Promise.all([loadRecentRuns(), loadRecentEvidence(), loadMissionWorklog()]);
        setQuickReplyStatus("Transcript saved as evidence.");
      } catch (e) { setQuickReplyStatus(`Save failed: ${e.message || e}`, true); }
    });
    const mStop = document.getElementById("modal-stop");
    if (mStop) mStop.addEventListener("click", async () => {
      const sid = state.selectedThreadId;
      if (!sid) return;
      try { await requestJson(`${MCH}/sessions/${encodeURIComponent(sid)}/runner/stop`, { method: "POST" }); } catch (e) {}
      refreshLiveMonitor();
    });
    const mClose = document.getElementById("modal-close");
    if (mClose) mClose.addEventListener("click", closeLiveCLIMonitor);

    document.querySelectorAll("[data-quick-reply]").forEach((button) => {
      button.addEventListener("click", () => {
        const key = button.getAttribute("data-quick-reply");
        if (key) sendQuickReply(key);
      });
    });

    // close monitor on backdrop
    const mon = document.getElementById("live-cli-modal");
    if (mon) mon.addEventListener("click", (e) => { if (e.target === mon) closeLiveCLIMonitor(); });

    const transcript = document.getElementById("modal-transcript");
    if (transcript && !transcript.dataset.scrollBound) {
      transcript.dataset.scrollBound = "1";
      transcript.addEventListener("scroll", () => {
        if (state.liveScrollProgrammatic) {
          state.liveScrollProgrammatic = false;
          return;
        }
        if (!isModalTranscriptNearBottom(transcript)) {
          pauseLiveAutoScroll();
        }
      });
    }

    updateLiveMonitorChrome();
  }

  // Init
  async function init() {
    // Hide any remaining old complex UI elements (from previous full cockpit) - force SIMPLE MODE
    const oldSelectors = [".rail", ".panel", "#sessions-list", "#queue-list", "#artifact-list", "#evidence-list", "#gate-list", "#safety-list", "#log-hint", "section.layout-stack", "main.panel"];
    oldSelectors.forEach((sel) => {
      document.querySelectorAll(sel).forEach((el) => {
        if (el.id && (el.id.includes("modal") || el.id === "codex-card" || el.id.includes("use-agent"))) return;
        el.style.display = "none";
      });
    });
    document.querySelectorAll("body > section.layout-stack, body > div.layout-stack").forEach((el) => {
      el.style.display = "none";
    });

    wireSimpleUI();
    if (window.WardenControlRoom && window.WardenControlRoom.init) {
      window.WardenControlRoom.init();
    }
    setActiveSection("mission");
    await Promise.all([loadLibraryStatus(), loadCaptainDeckStatus(), loadRecentRuns(), loadRecentEvidence(), loadActiveCaptainPlan(), loadMissionWorklog(), loadRecentGates()]);
    if (window.WardenControlRoom && window.WardenControlRoom.refresh) {
      await window.WardenControlRoom.refresh({ quiet: true });
    }

    // initial status check for disabled note etc is handled in deploy
    // If user has runner flags in this process (e.g. private), card will reflect Ready
  }

  // expose a couple for console/manual if needed
  window.McHarnessSimple = { deployPrompt, openLiveCLIMonitor, refreshLiveMonitor };
  window.WardenApp = { setActiveSection, openCaptainDeckModal, openLiveCLIMonitor };

  // boot
  init().catch((e) => console.error("init error", e));
})();
