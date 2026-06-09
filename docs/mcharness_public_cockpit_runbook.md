# McHarness Public Cockpit Runbook

## Service

- Service name: `mcharness-cockpit.service`
- Unit file: `/etc/systemd/system/mcharness-cockpit.service`
- Source unit file in repo: `deploy/systemd/mcharness-cockpit.service`

## Runtime

- Working directory: `/root/mcharness-public-export`
- Python executable: `/root/hybrid-agent-os/.venv/bin/python`
- Uvicorn import target: `src.server.api:app`
- Bind address: `127.0.0.1:8124`
- Public mode: `public_manual`
- Public writes: dangerous worker-style routes disabled by default

## Commands

- Start or enable: `sudo systemctl enable --now mcharness-cockpit.service`
- Stop: `sudo systemctl stop mcharness-cockpit.service`
- Restart: `sudo systemctl restart mcharness-cockpit.service`
- Status: `sudo systemctl status --no-pager mcharness-cockpit.service`
- Logs: `journalctl -u mcharness-cockpit.service -f`

## Health

- Backend health: `curl -s http://127.0.0.1:8124/api/mcharness/health`
- Live cockpit: `curl -I https://mctable.team/`
- Functional cockpit: `curl -I https://mctable.team/web/mctable-studio/cockpit-app.html`

## Rollback

- Backup path: `/root/mcharness-deploy-backups/<timestamp>`
- Restore cockpit assets:
  - `cp -a "$BACKUP_DIR"/. /root/mcharness-public-export/`
- Restore nginx if needed:
  - `sudo cp -a "$BACKUP_DIR/nginx-mctable-team.conf" /etc/nginx/sites-available/mctable-team`
  - `sudo nginx -t && sudo systemctl reload nginx`

## Safety Mode

- `SERVER CONTROL PLANE`
- `ALLOWLISTED CLI LANES ONLY`
- `ARBITRARY COMMAND EXECUTION DISABLED`
- `PUBLIC REAL AGENT LAUNCH DISABLED`
- `FAKE/MANUAL MODE`

## Current Limitations

- The public cockpit is manual/demo-first.
- Dangerous worker-style mutation routes are blocked when `MCHARNESS_PUBLIC_WRITE_ENABLED=false`.
- No real Codex, AGY, or other CLI runner is launched by the public service yet.
- The backend remains local to `127.0.0.1:8124` and is reached through nginx proxying.
