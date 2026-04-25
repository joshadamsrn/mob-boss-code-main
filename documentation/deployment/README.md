# Production Deployment Runbook

This runbook is the repo-local source of truth for production deployment to `mobboss-prod`.

## Access Rules

- SSH to production with the configured key and host alias: `ssh mobboss-prod`
- Use an interactive TTY session.
- Do not use a single quoted remote SSH command.
- Do not ask for a password unless key-based login fails.
- After login, change to `/root/mob-boss-code-main`.

## Deployment Sequence

Run one command at a time. Inspect the result after each command. If a command fails or hangs, diagnose before continuing.

1. `git pull --ff-only origin main`
   - Confirm the deployed commit hash from the pull output.
2. `npm run build`
   - Webpack warnings are acceptable only if the build completes successfully.
3. `/root/mob-boss-code-main/venv/bin/python3 project/mobboss_apps/manage.py collectstatic --noinput`
4. `mkdir -p /var/www/mobboss/static`
5. `rsync -av --delete /root/mob-boss-code-main/project/mobboss_apps/staticfiles/ /var/www/mobboss/static/`
6. `systemctl restart mobboss`

## Required `mobboss` Health Checks

Do not assume the restart succeeded. Run these checks in order:

1. `systemctl status mobboss --no-pager -l`
2. `ss -ltnp | grep 8000`
3. `curl -I --max-time 5 http://127.0.0.1:8000/auth/`

Success criteria:

- `systemctl status` shows `active (running)`, not `deactivating`
- gunicorn is listening on `127.0.0.1:8000`
- local `/auth/` returns `HTTP/1.1 200 OK`

Important:

- The real readiness gate is `curl -I --max-time 5 http://127.0.0.1:8000/auth/`.
- `active (running)` plus a listening socket is not sufficient by itself.

## Recovery Flow If `mobboss` Fails Health Checks

If any `mobboss` check fails, do not continue to nginx.

1. Re-run `systemctl status mobboss --no-pager -l`
   - If the service is still coming up, wait briefly and check again.
2. If it is stuck in `deactivating (stop-sigterm)`, wait briefly and re-check.
3. If it remains stuck, inspect the port:
   - `ss -ltnp | grep 8000`
4. If a stale gunicorn process is still holding `127.0.0.1:8000`, clear it.
5. Confirm port `8000` is free:
   - `ss -ltnp | grep 8000`
   - Expected result: no listener on `8000`
6. Start the service cleanly:
   - `systemctl start mobboss`
7. Repeat the three health checks until all pass.

Notes from the 2026-03-30 deployment:

- `systemctl restart mobboss` can leave the service stuck in `deactivating (stop-sigterm)`.
- A stale gunicorn worker can continue holding port `8000` after the master begins shutdown.
- Manual gunicorn checks may pass while the systemd-managed service path is still unhealthy, so use the real service health checks above as the source of truth.

## Nginx And Public Health

Only after `mobboss` passes all local health checks:

7. `systemctl restart nginx`
8. `nginx -t`
9. `curl -I --max-time 5 http://134.199.226.15/`

Success criteria:

- `nginx -t` succeeds
- the public curl does not hang
- expected public result is `HTTP/1.1 302 Found` redirecting to `/auth/?next=/`

## What To Report After Deployment

Always summarize:

- deployed commit
- whether `mobboss` needed recovery
- final `systemctl status`
- final local `/auth/` result
- final public HTTP result

## HTTPS Hardening

The current server can only become browser-trusted HTTPS if a real domain points to the droplet. A raw public IP is not sufficient for normal Let's Encrypt issuance.

Required DNS state:

1. Choose a domain such as `play.example.com`
2. Point an `A` record for that host to `134.199.226.15`
3. Wait for DNS propagation before running certificate setup

Required Django environment for HTTPS:

- `DJANGO_ALLOWED_HOSTS=play.example.com`
- `DJANGO_CSRF_TRUSTED_ORIGINS=https://play.example.com`
- `DJANGO_HTTPS_ENABLED=1`
- `DJANGO_SECURE_HSTS_SECONDS=31536000`

Required nginx outcome:

- listen on `443 ssl http2`
- redirect `http://` to `https://`
- forward `X-Forwarded-Proto https` to gunicorn
- serve the Let's Encrypt certificate for the chosen host

Recommended verification after HTTPS is enabled:

1. `curl -I http://play.example.com/`
   - Expected: `301` or `308` redirect to `https://play.example.com/`
2. `curl -I https://play.example.com/`
   - Expected: successful HTTPS response with a valid certificate chain
3. `curl -I https://play.example.com/auth/`
   - Expected: secure response and secure cookie behavior from Django
