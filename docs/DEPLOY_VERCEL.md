# Deploying with Vercel (hybrid: SPA on Vercel + backend on a container host)

Vercel hosts the **React SPA only**. The FastAPI backend (embedding model,
background workers, WebSockets, Postgres/Redis/ChromaDB/Neo4j) **cannot run on
Vercel** — it needs a long-running container host. This guide wires the two
together so HttpOnly-cookie auth keeps working.

```
Browser ──▶ Vercel (SPA)  ──/api (rewrite)──▶  Backend (Render/Fly/Railway/VM)
        └──────────────── wss://api.domain ───▶  (WebSockets, see §4)
```

## 1. Deploy the backend first (pick one host)

The backend ships a production `Dockerfile` + `docker-compose.prod.yml`.

- **Render / Railway / Fly.io** (easiest): deploy `backend/Dockerfile` as a web
  service; add managed **PostgreSQL** and **Redis** add-ons; set env vars (below).
  Run migrations once: `bash scripts/entrypoint.sh` (or a one-off `alembic upgrade head`).
- **VM / AWS / Azure:** use `deploy/bootstrap.sh` (see `docs/DEPLOYMENT.md`).

Backend env (from `deploy/generate-secrets.sh`, plus):
```
APP_ENV=production
COOKIE_SECURE=true
# §3 chooses SameSite + domain + CORS
LLM_API_KEY=...                 # Groq/OpenAI-compatible
READONLY_POSTGRES_USER=hc_readonly
READONLY_POSTGRES_PASSWORD=...
PHI_ENCRYPTION_KEYS=...
```
Note your backend's public HTTPS URL, e.g. `https://hc-api.onrender.com`.

## 2. Point the SPA at the backend

Edit `frontend/vercel.json` — replace `YOUR_BACKEND_DOMAIN` with your backend host:
```json
{ "source": "/api/:path*", "destination": "https://hc-api.onrender.com/api/:path*" }
```
This makes the browser call **same-origin** `/api`, so your existing
`SameSite=Lax` cookies work with **no CORS** config needed.

## 3. Deploy the SPA on Vercel
- New Project → import the repo → **Root Directory: `frontend`**.
- Framework preset: **Vite** (auto-detected). Build `npm run build`, output `dist`.
- Deploy. Visit the Vercel URL and log in.

## 4. Two cookie strategies (pick one)

**A. Quick start — Vercel rewrite (default vercel.json).** SPA → same-origin
`/api` → proxied to backend. `COOKIE_SAMESITE=lax` works. ✅ REST + the SSE chat
stream. ⚠️ **WebSockets are NOT proxied by Vercel rewrites** — the realtime
analytics socket won't connect in this mode (core chat still works via SSE).

**B. Recommended — custom domain (everything works, incl. WebSockets).**
Put both under one registrable domain:
- Frontend: `app.yourdomain.com` (Vercel custom domain)
- Backend: `api.yourdomain.com` (your container host, with TLS)

Then on the backend set:
```
COOKIE_DOMAIN=.yourdomain.com
COOKIE_SAMESITE=lax
CORS_ALLOWED_ORIGINS=https://app.yourdomain.com
```
and in the SPA set `VITE_WS_URL=wss://api.yourdomain.com`. Cookies are sent to
both subdomains (same site), CORS allows the SPA, and WS auth rides the cookie.

> Avoid `SameSite=None` unless you add CSRF tokens — it lets cross-site requests
> carry the auth cookie. Strategy B (shared parent domain) keeps `Lax` and is the
> secure, fully-functional choice.

## 5. Checklist
- [ ] Backend deployed, migrations applied, `hc_readonly` role provisioned
- [ ] `vercel.json` rewrite (A) or `COOKIE_DOMAIN`+CORS (B) configured
- [ ] `COOKIE_SECURE=true`, HTTPS on both ends
- [ ] Login works; chat returns results; (B only) realtime WS connects
- [ ] HIPAA: backend host is HIPAA-eligible with a BAA before real PHI
