# McHarness Private Codex Runner Smoke Runbook

**Purpose**: Exercise the *real* gated `codex_cli` lane (tmux + `codex exec`) in a completely private, local-only server on `127.0.0.1:8125`. The public `mctable.team` / `mcharness-cockpit.service` (port 8124) **must remain runner-disabled at all times**.

This is for personal/manual smoke only. No automated tests ever run real Codex.

**Current baseline commit**: `ac3fc9e` (or later with gated Codex foundation).

## Strict Rules (do not violate)

- Never set the Codex runner envs on the public systemd service.
- Never restart `mcharness-cockpit.service`.
- Never modify public nginx config or expose 8125.
- Never commit transcripts, artifacts, or logs that may contain sensitive output.
- Never inspect `~/.codex` tokens, cookies, or auth files.
- Public health must continue to report runner disabled (or flags absent/None in the long-running public process).
- All real Codex usage happens only in this private 8125 process under your direct control.

## Prerequisites (McServer)

- `codex` in PATH and authenticated for the user that will run the private server (e.g. `codex doctor` succeeds or shows healthy auth).
- `tmux` available.
- Source tree at `/root/mcharness-public-export` (the tree containing `ac3fc9e`+).
- Python venv at `/root/hybrid-agent-os/.venv`.
- Write access to `/var/lib/mcharness-cockpit-private` (or choose another DATA_ROOT you control).

## 1. Start the Private Server (manual, isolated)

Run this in a dedicated `screen` / `tmux` / `nohup` session on McServer (do **not** use the public service).

Exact command with the required environment:

```bash
MCHARNESS_DATA_ROOT=/var/lib/mcharness-cockpit-private \
MCHARNESS_PUBLIC_WRITE_ENABLED=true \
MCHARNESS_TMUX_RUNNER_ENABLED=true \
MCHARNESS_CODEX_RUNNER_ENABLED=true \
PYTHONPATH=/root/mcharness-public-export \
/root/hybrid-agent-os/.venv/bin/python -m uvicorn src.server.api:app \
  --host 127.0.0.1 --port 8125 --log-level info
```

Key points:
- Different `DATA_ROOT` isolates all runner state, artifacts, transcripts, sessions from the public instance.
- `PUBLIC_WRITE_ENABLED=true` only for this private instance (allows creating sessions, queuing prompts, starting runners, saving evidence).
- Both `*_RUNNER_ENABLED=true` are required to unlock the real `codex_cli` controlled path.
- `--host 127.0.0.1 --port 8125` keeps it localhost-only.
- Use `info` log level during smoke so you can watch the tmux/Codex startup.
- The public 8124 process (systemd) is untouched and continues to load whatever code it had at start time (runner disabled).

Recommended: run inside `screen -S private-codex` or a personal tmux window so you can detach.

## 2. Verify the Private Instance (health + lanes)

While the private uvicorn is running:

```bash
curl -s http://127.0.0.1:8125/api/mcharness/health | python3 -c '
import sys, json
d = json.load(sys.stdin)
print("ok:", d.get("ok"))
print("mode:", d.get("mode"))
print("real_agent_launch_enabled:", d.get("real_agent_launch_enabled"))
print("public_write_enabled:", d.get("public_write_enabled"))
print("tmux_runner_enabled:", d.get("tmux_runner_enabled"))
print("codex_runner_enabled:", d.get("codex_runner_enabled"))
print("manual_mode:", d.get("manual_mode"))
'
```

Expected (with the envs above):
- `tmux_runner_enabled: true`
- `codex_runner_enabled: true`
- `real_agent_launch_enabled: false`
- `public_write_enabled: true`

Check lanes (codex_cli should report installed + controlled_run_ready when the envs are active):

```bash
curl -s http://127.0.0.1:8125/api/mcharness/agent-lanes | python3 -c '
import sys, json
data = json.load(sys.stdin)
for l in data.get("lanes", []):
    if l.get("lane_id") == "codex_cli":
        print(json.dumps(l, indent=2))
'
```

## 3. Access the Private Cockpit UI

### Option A — From the McServer itself (no tunnel)
Open a browser on the server (or use `lynx`/`w3m` for quick check) and go to:

```
http://127.0.0.1:8125/web/mctable-studio/cockpit-app.html
```

### Option B — From your laptop (SSH tunnel)
From your laptop:

```bash
ssh -L 8125:127.0.0.1:8125 -N -f youruser@McServer
```

Then browse:

```
http://localhost:8125/web/mctable-studio/cockpit-app.html
```

(The tunnel forwards only to localhost on the server; nothing is public.)

## 4. Safe Read-Only Codex Smoke Prompt

Use a prompt that is deliberately read-only / proof-only. Tell Codex to be ephemeral and avoid any writes or git operations.

Example prompt text (copy into the queue prompt or session objective/plan):

```
PRIVATE SMOKE TEST — READ ONLY

You are participating in a controlled read-only smoke test of the McHarness private runner.

Instructions:
- Print exactly one proof line and nothing else in your final output:
  MCHARNESS_PRIVATE_CODEX_SMOKE_PROOF_LINE_42
- Do not execute any shell commands that write files, do not touch git, do not create directories.
- Prefer --ephemeral / read-only sandbox modes if offered.
- Stop immediately after emitting the proof line.

Output only the proof line in your last message.
```

You can also feed a very short prompt via the queue item:
`Print exactly: MCHARNESS_PRIVATE_CODEX_SMOKE_PROOF_LINE_42 . Use read-only mode only. Emit only the proof line.`

## 5. Cockpit Click Path (Private Instance)

1. Open the private cockpit UI (see section 3).
2. In "New Session":
   - Repo / worktree: select an allowlisted repo (e.g. `/root/mcharness-public-export`)
   - CLI agent lane: select `codex_cli` (it should now show as installed + controlled_run_ready because the private envs are set)
   - Fill Title, Objective, Plan Instruction (use the safe prompt above)
   - Click **New Session**
3. In the Prompt Queue section:
   - Add a queue item with the safe read-only prompt text.
   - Click **Queue Prompt**
4. Select the queued item → **Load Preview** (this creates the prompt artifact that will be fed to Codex).
5. With the queue item selected, click the **Start Codex Session (gated)** button (the button should be enabled for `codex_cli` in the private instance).
6. Watch:
   - **Refresh Status** — should go running → exited (or running if interactive).
   - The UI should display the tmux session name and an **attach command** (e.g. `tmux attach -t mch_...`).
   - **Refresh Transcript** — should contain the proof line (or at minimum the wrapper exit code) + any output Codex produced.
7. (Optional) In another terminal on the server: `tmux attach -t <name>` to watch live (then detach with Ctrl-b d).
8. Click **Save Transcript as Evidence** — this creates a `runner_transcript` + `evidence` artifact under the session (visible in the Evidence / Artifacts lists and usable with proof gates).
9. Click **Stop Runner** when done.
10. Optionally check the repo `git status` (the safe prompt should have produced zero changes).

You should see the runner state persisted under the private `MCHARNESS_DATA_ROOT`, visible via the private `/runner/status`, `/runner/transcript`, and `/runner/transcript-to-evidence` endpoints.

## 6. Health Output Verification (Private)

After starting the private server with the four envs, the health endpoint on 8125 must show the runner flags true (see section 2). This is the proof that the gated real Codex path is unlocked for this instance only.

The public 8124 health continues to show the runner flags as absent/None/false (live public process was never restarted with the enabling envs).

## 7. Helper Script (Manual Only — Not for Tests)

For convenience you may create a throw-away wrapper on the server (do **not** commit it, do **not** run it from pytest):

```bash
cat > /tmp/start-private-codex.sh << 'EOT'
#!/bin/bash
set -euo pipefail
export MCHARNESS_DATA_ROOT=/var/lib/mcharness-cockpit-private
export MCHARNESS_PUBLIC_WRITE_ENABLED=true
export MCHARNESS_TMUX_RUNNER_ENABLED=true
export MCHARNESS_CODEX_RUNNER_ENABLED=true
export PYTHONPATH=/root/mcharness-public-export
exec /root/hybrid-agent-os/.venv/bin/python -m uvicorn src.server.api:app \
  --host 127.0.0.1 --port 8125 --log-level info
EOT
chmod +x /tmp/start-private-codex.sh
```

Run it inside `screen -S private-codex /tmp/start-private-codex.sh`.

All automated tests (pytest + playwright) continue to exercise only `fake_test_lane` or the disabled paths. They never set the real Codex envs and never invoke real `codex`.

## 8. Cleanup After Smoke

- Kill the private uvicorn (Ctrl-C or `pkill -f "uvicorn.*8125"`).
- The private DATA_ROOT can be left or `rm -rf /var/lib/mcharness-cockpit-private` (your choice).
- The public service and `mctable.team` are completely unaffected.

## Summary — What Proves the Gated Codex Lane

- Public service health (8124) never enables the real runner.
- Private 8125 started with the exact four envs + different DATA_ROOT.
- `codex_cli` lane appears with `installed: true` and `runner_mode: controlled_run_ready` only in the private instance.
- Real `codex exec` is invoked via the tmux foundation when you press Start Codex (gated) in the private UI.
- Transcript capture + "Save as Evidence" work.
- Attach command is provided for manual observation.
- No changes to public nginx, no public exposure, no secrets printed or inspected, no automated real Codex usage.

This runbook is intended to be sufficient for a private smoke on the same night it is written.
