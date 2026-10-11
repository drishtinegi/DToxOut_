# DToxOut - Deployment Guide

## Architecture
```
Browser --HTTPS--> Caddy (TLS) --> nginx (SPA + /api proxy) --> FastAPI (gunicorn/uvicorn) --> PostgreSQL
```
The frontend is built to call `/api/v1` on its own origin, and nginx proxies that to the backend,
so there is no CORS or "wrong API URL" problem in production.

## Option A - One VPS with Docker Compose (simplest)
Any Ubuntu server with 2 GB+ RAM (Hetzner, DigitalOcean, AWS Lightsail, Azure VM...).

1. **Install Docker**: `curl -fsSL https://get.docker.com | sh`
2. **Point DNS**: create an `A` record `app.yourdomain.com` -> server IP. Open ports 80 and 443.
3. **Get the code** on the server (`git clone ...`) and create the env file:
   ```bash
   cp .env.example .env
   python3 -c "import secrets; print(secrets.token_urlsafe(48))"   # paste as JWT_SECRET_KEY
   nano .env    # set POSTGRES_PASSWORD, JWT_SECRET_KEY, DOMAIN
   ```
4. **Start**:
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
   ```
   On start the backend runs `prisma migrate deploy` automatically.
5. **Load reference data** (ingredients / regulations are not created by migrations):
   ```bash
   docker compose exec backend python scripts/import_regulations.py \
       --file data/regulations_batch.json --manifest data/manifest.json --dry-run   # validate first
   docker compose exec backend python scripts/import_regulations.py \
       --file data/regulations_batch.json --manifest data/manifest.json
   ```
   See `REGULATORY_DATA_GUIDE.md`. The bundled data is **fixture data** - replace it with verified
   data before presenting results to real users as safety advice.
6. **Create your admin user**:
   ```bash
   docker compose exec -e ADMIN_PASSWORD='a-long-password' backend \
       python scripts/create_admin.py --email you@domain.com --username admin
   ```
7. **Verify**: open `https://app.yourdomain.com`, register, and run a scan. Backend readiness: `docker compose exec backend curl -s localhost:8000/health/ready`.

**Updating**: `git pull && docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build`

**Backups**: `docker compose exec postgres pg_dump -U dtoxuser dtoxout | gzip > backup-$(date +%F).sql.gz` (cron it daily, copy off-server).

## Option B - Managed platforms (Render / Railway / Azure Container Apps / Fly.io)
Deploy as three pieces:
1. **PostgreSQL**: managed instance (Neon, Render Postgres, Azure Flexible Server). Copy its connection string.
2. **Backend**: build from `backend/Dockerfile`. Set env vars from `backend/.env.example`
   (`APP_ENV=production`, `DEBUG=false`, `DATABASE_URL`, `JWT_SECRET_KEY`, `CORS_ORIGINS=https://<frontend-url>`).
   Health check path: `/health/ready`. Migrations run on boot; set `RUN_MIGRATIONS=false` once you
   scale beyond 1 instance and run `prisma migrate deploy` as a release step instead.
3. **Frontend**: build from `frontend/Dockerfile` with `BACKEND_URL=https://<backend-internal-or-public-url>`
   (runtime env var; used by nginx). If the platform gives the backend a public URL on another domain,
   you may instead build with `--build-arg VITE_API_URL=https://<backend>/api/v1` and add that frontend
   origin to the backend's `CORS_ORIGINS`.

Set `TRUSTED_PROXY_COUNT` to the number of proxies between the internet and the backend
(1 behind nginx only; 2 behind a platform load balancer + nginx) so rate limiting sees real client IPs.

## Production checklist
- [ ] `JWT_SECRET_KEY` is 32+ random chars (app refuses to boot otherwise)
- [ ] `APP_ENV=production`, `DEBUG=false` (enforced at startup)
- [ ] HTTPS in front; `HSTS_MAX_AGE` enabled
- [ ] Postgres not exposed publicly; daily backups tested by restoring once
- [ ] `/docs` hidden (default in production)
- [ ] Uploads: `upload_data` volume persisted, or `STORAGE_PROVIDER=azure|s3`
      (build backend with `--build-arg STORAGE_EXTRAS=azure` or `s3`)
- [ ] Rate limiting is per-process memory; with more than 1 replica/worker the effective limit is multiplied
      (add a Redis storage URI to slowapi if you need strict global limits)
- [ ] Regulatory data replaced with verified, licensed data

## Troubleshooting
| Symptom | Cause / fix |
| --- | --- |
| Backend exits at boot with "Production configuration error" | Fix the named env var (secret length, DB URL, DEBUG, CORS) |
| Upload fails with 413 | Image > 5 MB (nginx limit is 6 MB; backend `MAX_UPLOAD_SIZE_BYTES`) |
| OCR returns "provider unavailable" | Tesseract missing: use the provided Dockerfile, or `OCR_PROVIDER=mock` for demos only |
| Everyone gets 429 | `TRUSTED_PROXY_COUNT` too low/0 behind a proxy: all users look like one IP |
| `migrate deploy` fails | Check `DATABASE_URL` and that `sslmode=require` is set for cloud DBs |
