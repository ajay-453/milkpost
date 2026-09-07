# Barnboard — Ops Runbook

*Stage 9 (final) of the AiNa App Factory pipeline · engine: local Claude*

## Deploy

**Target:** any Linux VPS or home server with Docker. No managed services.

```bash
docker build -t barnboard .
docker volume create barnboard-data
docker run -d --name barnboard --restart unless-stopped \
  -p 127.0.0.1:8000:8000 \
  -v barnboard-data:/app/data \
  -e DB_PATH=/app/data/barnboard.db \
  -e APP_NAME=Barnboard \
  barnboard
```

Bind to `127.0.0.1` and expose via one of:
- **Tailscale (recommended):** `tailscale serve 8000` — VPN-only access, HTTPS
  handled, calendar feed reachable from the farmer's phone on the tailnet.
- **LAN only:** publish on the LAN interface and firewall everything else.

> 🔐 **v1.1 adds login** (first-run setup page, 30-day sessions, PBKDF2
> passwords). Even so, keep Barnboard off the open internet — there is no
> HTTPS, rate limiting, or password reset. LAN or Tailscale remains the
> deployment posture. The calendar feed's secret-token URL bypasses login by
> design (calendar apps can't log in) — treat it like a password; rotate it by
> updating the `feed_token` row in the `settings` table.

Bare-metal alternative (no Docker): `python3 -m venv .venv && .venv/bin/pip
install -r requirements.txt && .venv/bin/uvicorn app.main:app --host 127.0.0.1
--port 8000` under a systemd unit with `Restart=always`.

## Monitoring

- **Health:** `GET /healthz` returns `ok`. Point UptimeKuma / a cron curl at it;
  alert after 2 consecutive failures.
- **Logs:** uvicorn writes access + error logs to stdout → `docker logs
  barnboard`. Zero tracebacks is the norm; any traceback is a bug worth filing.
- **Disk:** the SQLite file grows slowly (a 100-cow farm logs <1 MB/month).
  Alert at 90% disk anyway — it's a VPS.
- **SLO (informal):** the farm needs Barnboard twice a day. Anything fixed
  within a few hours never becomes an incident.

## Backup & restore

```bash
# nightly cron on the host — atomic-safe SQLite backup
docker exec barnboard python3 -c \
  "import sqlite3; sqlite3.connect('/app/data/barnboard.db').backup(sqlite3.connect('/app/data/backup-$(date +%a).db'))"
# then rsync/scp the backup file off the box
```

Seven rotating daily backups ≈ a few MB. **Restore:** stop the container, copy
the backup file over `barnboard.db`, start the container. Test the restore once
before go-live, not during your first incident.

## Incident runbook

| Symptom | Do this |
|---|---|
| Site down | `docker ps` → `docker restart barnboard` → check `docker logs --tail 50` |
| 500 on one page | `docker logs` for the traceback; the app has no external deps, so it's code or a corrupt DB |
| "Database is locked" | Almost impossible at farm traffic; if seen, restart the container (releases a stale handle) |
| Corrupt DB | Restore last night's backup (see above); at most one day of records re-entered from the tanker receipt |
| Bad deploy | `docker run` the previous image tag — the schema is additive, old code reads new DBs |
| Calendar feed not updating on phone | Calendar apps poll every 6–24 h; that's the app store's behavior, not a Barnboard fault |

## Go-live checklist

- [ ] Farm account created via the first-run setup page (strong password)
- [ ] Container runs with a **volume-mounted** `DB_PATH` (data survives rebuilds)
- [ ] `/healthz` monitored from outside the box
- [ ] Port 8000 NOT reachable from the public internet (verify with a phone off-WiFi)
- [ ] Nightly backup cron installed **and one restore rehearsed**
- [ ] Farmer's phone subscribed to `/calendar.ics` over the tailnet/LAN
- [ ] Real herd entered (or demo data cleared: stop container, delete DB file, start)
- [ ] The farmer has logged one real milking session end-to-end on their phone

## Cost

€4–6/month VPS, or €0 on an existing home server + Tailscale free tier.
No third-party services, no per-seat pricing, no surprise bills possible.
