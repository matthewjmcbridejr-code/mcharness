(function () {
  const MCH = "/api/mcharness";
  // Minimal state for Agent Library + Codex flow + Live Monitor
  const state = {
    repos: [],
    lanes: [],
    health: {},
    selectedThreadId: "",
    selectedQueueItemId: "",
    promptSubmittedAt: 0,
    liveMonitorExpanded: false,
    liveAutoScroll: true,
    lastMonitorTranscriptText: "",
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
      return status;
    } catch (e) {
      const deck = state.captainDeck;
      deck.configured = false;
      deck.planningEnabled = false;
      deck.privateKeySetupEnabled = false;
      deck.keySource = "missing";
      deck.notes = ["Captain status unavailable."];
      renderCaptainDeck();
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
      createBtn.disabled = !!deck.loading || !deck.configured;
      createBtn.textContent = deck.loading ? "Captain is building the plan..." : "Create Plan";
    }
    if (deployBtn) {
      deployBtn.disabled = !deck.plan;
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
    await Promise.all([populateCaptainDeckRepos(), loadCaptainDeckStatus()]);
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
    const deck = state.captainDeck;
    if (!deck.plan || !deck.plan.steps || !deck.plan.steps.length) return;
    const firstStep = deck.plan.steps[0];
    await deployRunnerPrompt({
      repoPath: deck.repoPath || "/root/mcharness-public-export",
      repoId: deck.repoId || "mcharness-public-export",
      title: deck.plan.title || deck.goal || "Captain plan",
      prompt: firstStep.prompt || deck.goal || "Implement the first Captain step.",
      noteId: "captain-deploy-note",
    });
    closeCaptainDeckModal();
  }

  // Load for library card status (from lanes + health)
  async function loadLibraryStatus() {
    try {
      const [lanesData, health] = await Promise.all([
        requestJson(`${MCH}/agent-lanes`),
        requestJson(`${MCH}/health`),
      ]);
      state.lanes = lanesData.lanes || [];
      state.health = health || {};
      const codex = state.lanes.find((l) => l.lane_id === "codex_cli") || {};
      const installed = !!codex.installed;
      const tmuxF = !!state.health.tmux_runner_enabled;
      const codexF = !!state.health.codex_runner_enabled;
      const line = document.getElementById("codex-status-line");
      if (line) {
        if (installed) {
          line.textContent = `Installed • ${tmuxF && codexF ? "Ready (gated)" : "Disabled in public (enable private 8125 + both MCHARNESS_*_RUNNER_ENABLED)"}`;
          line.style.color = (tmuxF && codexF) ? "var(--good, #63db9d)" : "var(--warn, #f0c66a)";
        } else {
          line.textContent = "Not detected on host";
          line.style.color = "var(--bad, #ff7e91)";
        }
      }
    } catch (e) {
      const line = document.getElementById("codex-status-line");
      if (line) line.textContent = "Status unavailable (public safe)";
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

  async function deployRunnerPrompt({ title, prompt, repoPath, repoId, closeCurrentModal = null, noteId = "deploy-disabled-note" }) {
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

      await requestJson(`${MCH}/sessions/${encodeURIComponent(sid)}/runner/start`, {
        method: "POST",
        body: { lane_id: "codex_cli", repo_id: repoId, queue_item_id: qid },
      });

      if (typeof closeCurrentModal === "function") closeCurrentModal();
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
          if (typeof refreshLiveMonitor === "function") await refreshLiveMonitor();
        } catch (e) {
          if (typeof refreshLiveMonitor === "function") await refreshLiveMonitor();
        }
      }, 10000);

      return sid;
    } catch (err) {
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
    setQuickReplyStatus(`Sending: ${key}`);
    try {
      const result = await requestJson(`${MCH}/sessions/${encodeURIComponent(sid)}/runner/send-key`, {
        method: "POST",
        body: { key },
      });
      setQuickReplyStatus(`Sent: ${key}`);
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

  // Wire simple UI events
  function wireSimpleUI() {
    const captainBtn = document.getElementById("develop-plan-btn");
    if (captainBtn) captainBtn.addEventListener("click", () => {
      openCaptainDeckModal().catch((e) => console.error(e));
    });

    // Use Agent
    const useBtn = document.getElementById("use-codex-btn");
    if (useBtn) useBtn.addEventListener("click", openUseAgentModal);

    const monBtn = document.getElementById("open-live-monitor-btn");
    if (monBtn) monBtn.addEventListener("click", openLiveCLIMonitor);

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
    });

    // Legacy toggle (show old if present)
    const legLink = document.getElementById("legacy-link");
    const leg = document.getElementById("legacy-cockpit");
    if (legLink && leg) {
      legLink.addEventListener("click", (e) => {
        e.preventDefault();
        leg.open = !leg.open;
      });
    }

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
        await requestJson(`${MCH}/sessions/${encodeURIComponent(sid)}/runner/transcript-to-evidence`, { method: "POST" });
        alert("Transcript saved as evidence.");
      } catch (e) { alert("Save failed: " + e.message); }
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
        if (el.id && (el.id.includes("modal") || el.id === "legacy-cockpit" || el.id === "codex-card" || el.id.includes("use-agent"))) return;
        el.style.display = "none";
      });
    });
    // Also hide any direct body children that are old sections after our main
    document.querySelectorAll("body > section, body > div:not([id*='modal']):not([id='legacy-cockpit'])").forEach((el) => {
      if (el.tagName === "HEADER" || el.tagName === "MAIN" || (el.id && el.id.includes("modal"))) return;
      el.style.display = "none";
    });

    wireSimpleUI();
    await loadLibraryStatus();

    // initial status check for disabled note etc is handled in deploy
    // If user has runner flags in this process (e.g. private), card will reflect Ready
  }

  // expose a couple for console/manual if needed
  window.McHarnessSimple = { deployPrompt, openLiveCLIMonitor, refreshLiveMonitor };

  // boot
  init().catch((e) => console.error("init error", e));
})();
