(function () {
  const MCH = "/api/mcharness";
  const MARIUS = "/api/marius";
  const POLL_MS = 3000;
  const STORAGE_KEY = "mcharness.selectedThreadId";

  const state = {
    repos: [],
    lanes: [],
    threads: [],
    thread: null,
    run: null,
    captain: null,
    queue: [],
    assignments: [],
    artifacts: [],
    evidence: [],
    gates: [],
    events: [],
    transitions: [],
    tools: [],
    safetyProfiles: [],
    selectedThreadId: localStorage.getItem(STORAGE_KEY) || "",
    selectedQueueItemId: "",
    selectedGateId: "",
    previewText: "",
    refreshInFlight: false,
  };

  const els = {
    newSessionForm: document.getElementById("new-session-form"),
    repoSelect: document.getElementById("repo-select"),
    laneSelect: document.getElementById("lane-select"),
    refreshSessions: document.getElementById("refresh-sessions"),
    sessionsList: document.getElementById("sessions-list"),
    queueList: document.getElementById("queue-list"),
    artifactList: document.getElementById("artifact-list"),
    evidenceList: document.getElementById("evidence-list"),
    gateList: document.getElementById("gate-list"),
    safetyList: document.getElementById("safety-list"),
    sessionSummary: document.getElementById("session-summary"),
    queueForm: document.getElementById("queue-form"),
    previewTitle: document.getElementById("preview-title"),
    previewLoad: document.getElementById("preview-load"),
    previewCopy: document.getElementById("preview-copy"),
    previewDownload: document.getElementById("preview-download"),
    previewMarkExported: document.getElementById("preview-mark-exported"),
    promptPreview: document.getElementById("prompt-preview"),
    evidenceForm: document.getElementById("evidence-form"),
    assignmentSelect: document.getElementById("assignment-select"),
    evidenceSummary: document.getElementById("evidence-summary"),
    evidenceSourceRef: document.getElementById("evidence-source-ref"),
    evidenceVerdict: document.getElementById("evidence-verdict"),
    evidenceOutput: document.getElementById("evidence-output"),
    gitStatusInput: document.getElementById("git-status-input"),
    gitDiffInput: document.getElementById("git-diff-input"),
    testOutputInput: document.getElementById("test-output-input"),
    completeAssignment: document.getElementById("complete-assignment"),
    activityLog: document.getElementById("activity-log"),
    runStatus: document.getElementById("run-status"),
    currentGate: document.getElementById("current-gate"),
    gateNote: document.getElementById("gate-note"),
    gateApprove: document.getElementById("gate-approve"),
    gateReject: document.getElementById("gate-reject"),
    gateMoreEvidence: document.getElementById("gate-more-evidence"),
    pauseSession: document.getElementById("pause-session"),
    resumeSession: document.getElementById("resume-session"),
    stopSession: document.getElementById("stop-session"),
    captureGitStatus: document.getElementById("capture-git-status"),
    reloadSession: document.getElementById("reload-session"),
  };

  let pollHandle = null;

  function escapeHtml(value) {
    return String(value || "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function lines(value) {
    return String(value || "")
      .split(/\n|,/)
      .map((item) => item.trim())
      .filter(Boolean);
  }

  function formatDate(value) {
    if (!value) return "n/a";
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? String(value) : parsed.toLocaleString();
  }

  function slugify(value) {
    return String(value || "session")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 48) || "session";
  }

  async function requestJson(path, options) {
    const response = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    if (!response.ok) {
      let detail = `${response.status} ${response.statusText}`;
      try {
        const payload = await response.json();
        detail = payload.detail || payload.reason || JSON.stringify(payload);
      } catch (error) {
        detail = await response.text();
      }
      throw new Error(detail);
    }
    return response.json();
  }

  async function writeRunEvent(title, detail, severity, eventType) {
    if (!state.run) return;
    await requestJson(`${MARIUS}/workbench/runs/${encodeURIComponent(state.run.run_id)}/events`, {
      method: "POST",
      body: JSON.stringify({
        event_type: eventType || "note",
        title,
        detail,
        severity: severity || "info",
      }),
    });
  }

  function currentThreadMetadata() {
    return (state.thread && state.thread.metadata) || {};
  }

  function activeQueueItem() {
    if (!state.queue.length) return null;
    if (state.selectedQueueItemId) {
      const selected = state.queue.find((item) => item.queue_item_id === state.selectedQueueItemId);
      if (selected) return selected;
    }
    return state.queue[0];
  }

  function activeGate() {
    if (!state.gates.length) return null;
    if (state.selectedGateId) {
      const selected = state.gates.find((gate) => gate.gate_id === state.selectedGateId);
      if (selected) return selected;
    }
    return state.gates.find((gate) => gate.status === "open") || state.gates[0];
  }

  async function loadControlPlaneMetadata() {
    const [reposPayload, lanesPayload, tools, safetyProfiles] = await Promise.all([
      requestJson(`${MCH}/repos`),
      requestJson(`${MCH}/agent-lanes`),
      requestJson(`${MARIUS}/workbench/tools`),
      requestJson(`${MARIUS}/workbench/safety-profiles`),
    ]);
    state.repos = reposPayload.repos || [];
    state.lanes = lanesPayload.lanes || [];
    state.tools = tools;
    state.safetyProfiles = safetyProfiles;
    renderRepoOptions();
    renderLaneOptions();
    renderSafety();
  }

  async function loadThreads() {
    state.threads = await requestJson(`${MARIUS}/workbench/threads`);
    if (!state.selectedThreadId && state.threads.length) {
      state.selectedThreadId = state.threads[0].thread_id;
      localStorage.setItem(STORAGE_KEY, state.selectedThreadId);
    }
    renderThreads();
  }

  async function refreshSelectedSession() {
    if (!state.selectedThreadId || state.refreshInFlight) return;
    state.refreshInFlight = true;
    try {
      state.thread = await requestJson(`${MARIUS}/workbench/threads/${encodeURIComponent(state.selectedThreadId)}`);
      const runs = await requestJson(`${MARIUS}/workbench/threads/${encodeURIComponent(state.selectedThreadId)}/runs`);
      state.run = runs[0] || null;
      state.captain = null;
      state.queue = [];
      state.assignments = [];
      state.artifacts = [];
      state.evidence = [];
      state.gates = [];
      state.events = [];
      state.transitions = [];
      const artifactPayload = await requestJson(`${MCH}/sessions/${encodeURIComponent(state.selectedThreadId)}/artifacts`);
      state.artifacts = artifactPayload.artifacts || [];
      if (state.run) {
        const runId = encodeURIComponent(state.run.run_id);
        const [events, evidence, gates] = await Promise.all([
          requestJson(`${MARIUS}/workbench/runs/${runId}/events`),
          requestJson(`${MARIUS}/workbench/runs/${runId}/evidence`),
          requestJson(`${MARIUS}/workbench/runs/${runId}/proof-gates`),
        ]);
        state.events = events;
        state.evidence = evidence;
        state.gates = gates;
        if (!state.selectedGateId && gates.length) {
          state.selectedGateId = gates[0].gate_id;
        }
        try {
          const [captain, queue, assignments, transitions] = await Promise.all([
            requestJson(`${MARIUS}/captain/runs/${runId}`),
            requestJson(`${MARIUS}/captain/runs/${runId}/queue`),
            requestJson(`${MARIUS}/captain/runs/${runId}/assignments`),
            requestJson(`${MARIUS}/captain/runs/${runId}/transitions`),
          ]);
          state.captain = captain;
          state.queue = queue;
          state.assignments = assignments;
          state.transitions = transitions;
          if (!state.selectedQueueItemId && queue.length) {
            state.selectedQueueItemId = queue[0].queue_item_id;
          }
        } catch (error) {
          state.captain = null;
        }
      }
      renderSession();
    } finally {
      state.refreshInFlight = false;
    }
  }

  function renderRepoOptions() {
    els.repoSelect.innerHTML = state.repos
      .map((repo) => `<option value="${escapeHtml(repo.path)}">${escapeHtml(repo.path)}</option>`)
      .join("");
  }

  function renderLaneOptions() {
    els.laneSelect.innerHTML = state.lanes
      .map((lane) => `<option value="${escapeHtml(lane.lane_id)}" ${lane.implemented ? "" : "disabled"}>${escapeHtml(lane.title)}${lane.implemented ? "" : " (placeholder)"}</option>`)
      .join("");
  }

  function renderThreads() {
    if (!state.threads.length) {
      els.sessionsList.innerHTML = '<div class="empty">No persisted sessions yet.</div>';
      return;
    }
    els.sessionsList.innerHTML = state.threads
      .map((thread) => {
        const active = thread.thread_id === state.selectedThreadId ? " active" : "";
        const metadata = thread.metadata || {};
        return `
          <button class="list-item${active}" type="button" data-thread-id="${escapeHtml(thread.thread_id)}">
            <h4>${escapeHtml(thread.title)}</h4>
            <small>${escapeHtml(thread.thread_id)}</small>
            <div class="pill">${escapeHtml(thread.status)}</div>
            <div class="muted">${escapeHtml(metadata.repo_path || "(repo pending)")}</div>
            <div class="muted">${escapeHtml(metadata.agent_lane || "(lane pending)")}</div>
          </button>
        `;
      })
      .join("");
    els.sessionsList.querySelectorAll("[data-thread-id]").forEach((button) => {
      button.addEventListener("click", async () => {
        state.selectedThreadId = button.dataset.threadId || "";
        state.selectedQueueItemId = "";
        state.selectedGateId = "";
        state.previewText = "";
        localStorage.setItem(STORAGE_KEY, state.selectedThreadId);
        await refreshSelectedSession();
        renderThreads();
      });
    });
  }

  function renderQueue() {
    if (!state.queue.length) {
      els.queueList.innerHTML = '<div class="empty">No queue items for the selected session.</div>';
      els.previewTitle.textContent = "No queue item selected";
      els.promptPreview.value = state.previewText || "";
      return;
    }
    els.queueList.innerHTML = state.queue
      .map((item) => {
        const active = item.queue_item_id === state.selectedQueueItemId ? " active" : "";
        return `
          <button class="list-item${active}" type="button" data-queue-id="${escapeHtml(item.queue_item_id)}">
            <h4>${escapeHtml(item.title)}</h4>
            <small>${escapeHtml(item.queue_item_id)}</small>
            <div class="pill">${escapeHtml(item.status)}</div>
            <div class="muted">Lane-ready prompt · ${escapeHtml(item.target_role)}</div>
          </button>
        `;
      })
      .join("");
    els.queueList.querySelectorAll("[data-queue-id]").forEach((button) => {
      button.addEventListener("click", () => {
        state.selectedQueueItemId = button.dataset.queueId || "";
        state.previewText = "";
        renderQueue();
      });
    });
    const current = activeQueueItem();
    els.previewTitle.textContent = current ? `${current.title} (${current.queue_item_id})` : "No queue item selected";
    els.promptPreview.value = state.previewText || "";
  }

  function renderArtifacts() {
    if (!state.artifacts.length) {
      els.artifactList.innerHTML = '<div class="empty">No artifacts recorded for this session yet.</div>';
      return;
    }
    els.artifactList.innerHTML = state.artifacts
      .map((artifact) => `
        <div class="card">
          <h4>${escapeHtml(artifact.title)}</h4>
          <div class="pill">${escapeHtml(artifact.kind)}</div>
          <p>${escapeHtml(artifact.summary || "")}</p>
          <small class="mono">${escapeHtml(artifact.path)}</small>
        </div>
      `)
      .join("");
  }

  function renderEvidence() {
    if (!state.evidence.length) {
      els.evidenceList.innerHTML = '<div class="empty">No evidence recorded for the current run.</div>';
      return;
    }
    els.evidenceList.innerHTML = state.evidence
      .map((item) => `
        <div class="card">
          <h4>${escapeHtml(item.title)}</h4>
          <div class="pill">${escapeHtml(item.verdict)}</div>
          <p>${escapeHtml(item.summary)}</p>
          <small>${escapeHtml(item.source_ref || "manual")} · ${escapeHtml(formatDate(item.created_at))}</small>
        </div>
      `)
      .join("");
  }

  function renderGates() {
    if (!state.gates.length) {
      els.gateList.innerHTML = '<div class="empty">No proof gates on the current run.</div>';
      els.currentGate.innerHTML = "<h4>No gate selected</h4><p class=\"muted\">The current run has no gate.</p>";
      return;
    }
    els.gateList.innerHTML = state.gates
      .map((gate) => {
        const active = gate.gate_id === activeGate()?.gate_id ? " active" : "";
        return `
          <button class="list-item${active}" type="button" data-gate-id="${escapeHtml(gate.gate_id)}">
            <h4>${escapeHtml(gate.title)}</h4>
            <small>${escapeHtml(gate.gate_id)}</small>
            <div class="pill">${escapeHtml(gate.status)}</div>
            <div class="muted">${escapeHtml(gate.reason)}</div>
          </button>
        `;
      })
      .join("");
    els.gateList.querySelectorAll("[data-gate-id]").forEach((button) => {
      button.addEventListener("click", () => {
        state.selectedGateId = button.dataset.gateId || "";
        renderGates();
      });
    });
    const gate = activeGate();
    els.currentGate.innerHTML = gate
      ? `
        <h4>${escapeHtml(gate.title)}</h4>
        <div class="pill">${escapeHtml(gate.status)}</div>
        <p>${escapeHtml(gate.reason)}</p>
        <small>Requires human: ${escapeHtml(String(gate.requires_human))}</small>
      `
      : "<h4>No gate selected</h4><p class=\"muted\">The current run has no gate.</p>";
  }

  function renderSafety() {
    const profileCards = state.safetyProfiles
      .map((profile) => `
        <div class="card">
          <h4>${escapeHtml(profile.title)}</h4>
          <p>${escapeHtml(profile.summary)}</p>
          <small>${escapeHtml(profile.notes || "")}</small>
        </div>
      `)
      .join("");
    const toolCards = state.tools
      .map((tool) => `
        <div class="card">
          <h4>${escapeHtml(tool.name)}</h4>
          <div class="pill">${escapeHtml(tool.status)}</div>
          <p>${escapeHtml(tool.summary)}</p>
        </div>
      `)
      .join("");
    els.safetyList.innerHTML = profileCards + toolCards;
  }

  function renderSessionSummary() {
    if (!state.thread) {
      els.sessionSummary.innerHTML = "<h4>No session selected</h4><p class=\"muted\">Create a session or reopen one from the left rail.</p>";
      return;
    }
    const metadata = currentThreadMetadata();
    const runLine = state.run ? `${state.run.run_id} · ${state.run.status}` : "No linked run";
    els.sessionSummary.innerHTML = `
      <h4>${escapeHtml(state.thread.title)}</h4>
      <p>${escapeHtml(state.thread.objective)}</p>
      <div class="kv-grid">
        <div class="stat"><small>Repo / worktree</small><strong class="mono">${escapeHtml(metadata.repo_path || "n/a")}</strong></div>
        <div class="stat"><small>CLI lane</small><strong>${escapeHtml(metadata.agent_lane || "n/a")}</strong></div>
        <div class="stat"><small>Session id</small><strong class="mono">${escapeHtml(state.thread.thread_id)}</strong></div>
        <div class="stat"><small>Run</small><strong class="mono">${escapeHtml(runLine)}</strong></div>
      </div>
    `;
  }

  function renderAssignments() {
    if (!state.assignments.length) {
      els.assignmentSelect.innerHTML = '<option value="">No assignment available</option>';
      return;
    }
    els.assignmentSelect.innerHTML = state.assignments
      .map((assignment) => `
        <option value="${escapeHtml(assignment.assignment_id)}">
          ${escapeHtml(assignment.title)} (${escapeHtml(assignment.status)})
        </option>
      `)
      .join("");
  }

  function renderRunStatus() {
    if (!state.run) {
      els.runStatus.innerHTML = '<div class="empty">No active run.</div>';
      return;
    }
    const metadata = currentThreadMetadata();
    const gate = activeGate();
    els.runStatus.innerHTML = `
      <div class="stat"><small>Run status</small><strong>${escapeHtml(state.run.status)}</strong></div>
      <div class="stat"><small>Captain state</small><strong>${escapeHtml((state.captain && state.captain.status) || "n/a")}</strong></div>
      <div class="stat"><small>Repo</small><strong class="mono">${escapeHtml(metadata.repo_path || "n/a")}</strong></div>
      <div class="stat"><small>Lane</small><strong>${escapeHtml(metadata.agent_lane || "n/a")}</strong></div>
      <div class="stat"><small>Artifacts</small><strong>${escapeHtml(String(state.artifacts.length))}</strong></div>
      <div class="stat"><small>Gate</small><strong>${escapeHtml(gate ? gate.status : "none")}</strong></div>
    `;
  }

  function renderTimeline() {
    const merged = [
      ...state.events.map((event) => ({
        kind: "event",
        title: event.title,
        detail: event.detail,
        created_at: event.created_at,
        status: event.severity,
      })),
      ...state.transitions.map((transition) => ({
        kind: "transition",
        title: `${transition.from_status} -> ${transition.to_status}`,
        detail: transition.reason,
        created_at: transition.created_at,
        status: "info",
      })),
    ].sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || "")));
    if (!merged.length) {
      els.activityLog.innerHTML = '<div class="empty">No persisted activity yet.</div>';
      return;
    }
    els.activityLog.innerHTML = merged
      .map((item) => `
        <div class="timeline-item">
          <div class="pill ${escapeHtml(item.status)}">${escapeHtml(item.kind)}</div>
          <h4>${escapeHtml(item.title)}</h4>
          <p>${escapeHtml(item.detail)}</p>
          <small>${escapeHtml(formatDate(item.created_at))}</small>
        </div>
      `)
      .join("");
  }

  function renderSession() {
    renderThreads();
    renderSessionSummary();
    renderQueue();
    renderArtifacts();
    renderEvidence();
    renderGates();
    renderAssignments();
    renderRunStatus();
    renderTimeline();
  }

  async function ensurePreviewText(markSent) {
    const item = activeQueueItem();
    if (!item) throw new Error("Select a queue item first.");
    if (state.previewText && item.queue_item_id === state.selectedQueueItemId && !markSent) {
      return state.previewText;
    }
    const payload = await requestJson(`${MCH}/sessions/${encodeURIComponent(state.selectedThreadId)}/prompt-export`, {
      method: "POST",
      body: JSON.stringify({
        queue_item_id: item.queue_item_id,
        mark_sent: Boolean(markSent),
      }),
    });
    state.previewText = payload.prompt_text || "";
    await refreshSelectedSession();
    els.promptPreview.value = state.previewText;
    return state.previewText;
  }

  async function handleNewSession(event) {
    event.preventDefault();
    const form = new FormData(els.newSessionForm);
    const payload = await requestJson(`${MCH}/sessions`, {
      method: "POST",
      body: JSON.stringify({
        title: String(form.get("title") || "").trim(),
        objective: String(form.get("objective") || "").trim(),
        plan_instruction: String(form.get("planInstruction") || "").trim(),
        repo_path: String(form.get("repoPath") || "").trim(),
        agent_lane: String(form.get("agentLane") || "").trim(),
      }),
    });
    state.selectedThreadId = payload.session_id;
    localStorage.setItem(STORAGE_KEY, state.selectedThreadId);
    els.newSessionForm.reset();
    renderRepoOptions();
    renderLaneOptions();
    await loadThreads();
    await refreshSelectedSession();
  }

  async function handleQueuePrompt(event) {
    event.preventDefault();
    if (!state.selectedThreadId) throw new Error("Create or select a session first.");
    const form = new FormData(els.queueForm);
    await requestJson(`${MCH}/sessions/${encodeURIComponent(state.selectedThreadId)}/queue`, {
      method: "POST",
      body: JSON.stringify({
        title: String(form.get("title") || "").trim(),
        prompt: String(form.get("prompt") || "").trim(),
        target_role: String(form.get("targetRole") || "reviewer"),
        file_scope: lines(form.get("fileScope")),
        forbidden_file_scope: lines(form.get("forbiddenFileScope")),
        acceptance_checks: lines(form.get("acceptanceChecks")),
        evidence_required: lines(form.get("evidenceRequired")),
      }),
    });
    els.queueForm.reset();
    await refreshSelectedSession();
  }

  async function handleCopyPreview() {
    const text = await ensurePreviewText(false);
    await navigator.clipboard.writeText(text);
    await writeRunEvent("Prompt copied", `Copied ${activeQueueItem().queue_item_id} to clipboard.`, "info", "artifact");
    await refreshSelectedSession();
  }

  async function handleDownloadPreview() {
    const item = activeQueueItem();
    const text = await ensurePreviewText(false);
    const filename = `${slugify(state.thread ? state.thread.title : "session")}-${item.queue_item_id}.md`;
    const blob = new Blob([text], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
    await writeRunEvent("Prompt downloaded", `Downloaded ${filename}.`, "info", "artifact");
    await refreshSelectedSession();
  }

  async function handleMarkExported() {
    await ensurePreviewText(true);
  }

  async function submitManualResult(completeAssignment) {
    if (!state.selectedThreadId) throw new Error("Create or select a session first.");
    const assignmentId = els.assignmentSelect.value || null;
    const summary = els.evidenceSummary.value.trim();
    if (!summary) throw new Error("Evidence summary is required.");
    await requestJson(`${MCH}/sessions/${encodeURIComponent(state.selectedThreadId)}/manual-result`, {
      method: "POST",
      body: JSON.stringify({
        assignment_id: assignmentId,
        summary,
        transcript: els.evidenceOutput.value.trim() || null,
        source_ref: els.evidenceSourceRef.value.trim() || null,
        verdict: els.evidenceVerdict.value,
        complete_assignment: Boolean(completeAssignment),
        git_status: els.gitStatusInput.value.trim() || null,
        git_diff_summary: els.gitDiffInput.value.trim() || null,
        test_output: els.testOutputInput.value.trim() || null,
      }),
    });
    await refreshSelectedSession();
  }

  async function handleGateDecision(decision) {
    if (!state.selectedThreadId) throw new Error("Create or select a session first.");
    await requestJson(`${MCH}/sessions/${encodeURIComponent(state.selectedThreadId)}/gate-decision`, {
      method: "POST",
      body: JSON.stringify({
        decision,
        note: els.gateNote.value.trim() || null,
        continue_after: false,
      }),
    });
    await refreshSelectedSession();
  }

  async function handleCaptureGitStatus() {
    if (!state.selectedThreadId) throw new Error("Create or select a session first.");
    const payload = await requestJson(`${MCH}/sessions/${encodeURIComponent(state.selectedThreadId)}/git-status`);
    els.gitStatusInput.value = payload.git_status || "";
    els.gitDiffInput.value = payload.git_diff_summary || "";
    await refreshSelectedSession();
  }

  async function handlePause() {
    if (!state.thread) throw new Error("Create or select a session first.");
    await requestJson(`${MARIUS}/workbench/threads/${encodeURIComponent(state.thread.thread_id)}`, {
      method: "PATCH",
      body: JSON.stringify({ status: "paused" }),
    });
    await writeRunEvent("Session paused", "Operator paused the session.", "warning", "note");
    await loadThreads();
    await refreshSelectedSession();
  }

  async function handleResume() {
    if (!state.run) throw new Error("Create or select a session with an active run first.");
    const payload = await requestJson(`${MARIUS}/captain/runs/${encodeURIComponent(state.run.run_id)}/continue`, {
      method: "POST",
      body: JSON.stringify({}),
    });
    await writeRunEvent("Continuation requested", `${payload.status}: ${payload.reason}`, payload.status === "ready_to_continue" ? "success" : "blocked", payload.status === "ready_to_continue" ? "note" : "blocked");
    await loadThreads();
    await refreshSelectedSession();
  }

  async function handleStop() {
    if (!state.thread) throw new Error("Create or select a session first.");
    await requestJson(`${MARIUS}/workbench/threads/${encodeURIComponent(state.thread.thread_id)}`, {
      method: "PATCH",
      body: JSON.stringify({ status: "closed" }),
    });
    await writeRunEvent("Session stopped", "Operator stopped the session.", "blocked", "blocked");
    await loadThreads();
    await refreshSelectedSession();
  }

  function bindEvents() {
    els.newSessionForm.addEventListener("submit", (event) => runAction(handleNewSession, event));
    els.refreshSessions.addEventListener("click", () => runAction(async () => {
      await loadThreads();
      await refreshSelectedSession();
    }));
    els.queueForm.addEventListener("submit", (event) => runAction(handleQueuePrompt, event));
    els.previewLoad.addEventListener("click", () => runAction(() => ensurePreviewText(false)));
    els.previewCopy.addEventListener("click", () => runAction(handleCopyPreview));
    els.previewDownload.addEventListener("click", () => runAction(handleDownloadPreview));
    els.previewMarkExported.addEventListener("click", () => runAction(handleMarkExported));
    els.evidenceForm.addEventListener("submit", (event) => runAction(async () => {
      event.preventDefault();
      await submitManualResult(false);
    }, event));
    els.completeAssignment.addEventListener("click", () => runAction(() => submitManualResult(true)));
    els.gateApprove.addEventListener("click", () => runAction(() => handleGateDecision("approved")));
    els.gateReject.addEventListener("click", () => runAction(() => handleGateDecision("rejected")));
    els.gateMoreEvidence.addEventListener("click", () => runAction(() => handleGateDecision("edit_requested")));
    els.captureGitStatus.addEventListener("click", () => runAction(handleCaptureGitStatus));
    els.pauseSession.addEventListener("click", () => runAction(handlePause));
    els.resumeSession.addEventListener("click", () => runAction(handleResume));
    els.stopSession.addEventListener("click", () => runAction(handleStop));
    els.reloadSession.addEventListener("click", () => runAction(refreshSelectedSession));
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) return;
      runAction(async () => {
        await loadThreads();
        await refreshSelectedSession();
      });
    });
  }

  async function runAction(action, event) {
    if (event && typeof event.preventDefault === "function") {
      event.preventDefault();
    }
    try {
      await action(event);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      window.alert(message);
    }
  }

  function startPolling() {
    if (pollHandle) {
      window.clearInterval(pollHandle);
    }
    pollHandle = window.setInterval(() => {
      if (document.hidden) return;
      runAction(async () => {
        await loadThreads();
        await refreshSelectedSession();
      });
    }, POLL_MS);
  }

  async function init() {
    bindEvents();
    await loadControlPlaneMetadata();
    await loadThreads();
    await refreshSelectedSession();
    startPolling();
  }

  init().catch((error) => {
    const message = error instanceof Error ? error.message : String(error);
    window.alert(message);
  });
})();
