(function () {
  const MCH = "/api/mcharness";
  // Minimal state for Agent Library + Codex flow + Live Monitor
  const state = {
    repos: [],
    lanes: [],
    health: {},
    selectedThreadId: "",
    selectedQueueItemId: "",
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

  function escapeHtml(v) {
    return String(v || "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
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

  // Deploy Prompt flow (create, queue, export, start, open monitor, delayed send)
  async function deployPrompt() {
    const repoSel = document.getElementById("modal-repo-select");
    const titleEl = document.getElementById("modal-task-title");
    const promptEl = document.getElementById("modal-prompt");
    const note = document.getElementById("deploy-disabled-note");
    if (!repoSel || !titleEl || !promptEl) return;

    const repoPath = repoSel.value || "/root/mcharness-public-export";
    const repoId = (repoSel.selectedOptions[0] && repoSel.selectedOptions[0].dataset.repoId) || "mcharness-public-export";
    const title = (titleEl.value || "Untitled task").trim();
    const prompt = (promptEl.value || "Perform the task described.").trim();

    if (!title || !prompt) {
      alert("Title and prompt are required.");
      return;
    }

    // Check flags for real codex (public usually false)
    const health = state.health || {};
    const canRunReal = !!(health.tmux_runner_enabled && health.codex_runner_enabled);
    if (!canRunReal) {
      if (note) {
        note.textContent = "Codex runner is disabled. Start private runner mode (8125 + both MCHARNESS_TMUX_RUNNER_ENABLED=true and MCHARNESS_CODEX_RUNNER_ENABLED=true) to use Deploy Prompt for real Codex.";
        note.style.display = "block";
      }
      // Still allow "dry" path or just show; for demo we can still create session/queue but not start real
      // For this task we proceed to create/queue/start (will be disabled on backend) and open monitor which will show disabled
    }

    try {
      // 1. create session (codex lane)
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

      // 2. queue the prompt
      const qres = await requestJson(`${MCH}/sessions/${encodeURIComponent(sid)}/queue`, {
        method: "POST",
        body: { title: "Task prompt", prompt },
      });
      const qid = qres.queue_item_id || qres.id;

      // 3. export to ensure artifact (optional but per flow)
      try {
        await requestJson(`${MCH}/sessions/${encodeURIComponent(sid)}/prompt-export`, {
          method: "POST",
          body: { queue_item_id: qid, mark_sent: false },
        });
      } catch (e) { /* non fatal */ }

      // 4. start the runner (backend respects flags; for codex will use the computed prompt path)
      await requestJson(`${MCH}/sessions/${encodeURIComponent(sid)}/runner/start`, {
        method: "POST",
        body: { lane_id: "codex_cli", repo_id: repoId, queue_item_id: qid },
      });

      // 5. close use modal, open live monitor
      closeUseAgentModal();
      openLiveCLIMonitor();  // reuses/extends previous monitor impl

      // 6. wait ~10s then send/inject the prompt (safe endpoint; only the modal prompt)
      setTimeout(async () => {
        try {
          await requestJson(`${MCH}/sessions/${encodeURIComponent(sid)}/runner/send-prompt`, {
            method: "POST",
            body: { prompt },
          });
          // refresh monitor to show output
          if (typeof refreshLiveMonitor === "function") await refreshLiveMonitor();
        } catch (e) {
          // if send not critical or not present, monitor will still show transcript from start/execution
          if (typeof refreshLiveMonitor === "function") await refreshLiveMonitor();
        }
      }, 10000);

    } catch (err) {
      alert("Deploy failed: " + (err.message || err));
      // still try to open monitor if sid
      if (state.selectedThreadId) openLiveCLIMonitor();
    }
  }

  // Live CLI Monitor (adapted from previous implementation, read-only, polls while open)
  let liveMonitorInterval = null;
  let liveAutoRefresh = true;

  function openLiveCLIMonitor() {
    const modal = document.getElementById("live-cli-modal");
    if (!modal) return;
    modal.style.display = "flex";
    setQuickReplyStatus("");
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
      if (laneEl) laneEl.textContent = status.lane_id || "Codex CLI";
      const infoEl = document.getElementById("modal-info");
      const statusText = status.status || "n/a";
      let friendly = statusText;
      if (statusText === "waiting_for_codex") friendly = "waiting for Codex to load (~10s)";
      else if (statusText === "prompt_sent") friendly = "prompt sent, live output below";
      else if (statusText === "running") friendly = "running (interactive tmux + Codex)";
      if (infoEl) {
        const debug = `exe: codex | cwd: ${status.repo_id || 'n/a'} | tmux: ${status.tmux_session_name || 'n/a'} | attach: ${status.attach_command || 'n/a'}`;
        infoEl.innerHTML = `Repo: ${status.repo_id || "n/a"} | Status: <strong>${friendly}</strong><br><small style="opacity:0.7">${debug}</small>`;
      }
      const pre = document.getElementById("modal-transcript");
      const txt = (trans && trans.transcript) ? trans.transcript : (status.transcript || "");
      let displayTxt = txt || "Waiting for CLI output...";
      if (pre) {
        pre.textContent = displayTxt;
        // warning if only exit code visible (means launch didn't keep interactive or capture missed TUI)
        if (displayTxt.trim() === "MCH_EXIT_CODE:0" || (displayTxt.trim().length < 30 && displayTxt.includes("EXIT"))) {
          pre.textContent = displayTxt + "\n\n[Warning] Runner exited before producing visible CLI output. Check flags, codex auth, or tmux attach manually.";
        }
      }
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
        pre.textContent = result.transcript_excerpt;
      }
      await refreshLiveMonitor();
    } catch (e) {
      setQuickReplyStatus(`Failed: ${e.message || e}`, true);
    }
  }

  // Wire simple UI events
  function wireSimpleUI() {
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
