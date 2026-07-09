# Deploy in 10 minutes

**Website** → Vercel (free)
**API** → Render (free)
**Login** → email + password, `@fifthspace.com` only

---

## Part 1 — Backend on Render (~5 min)

1. Go to [render.com](https://render.com) → sign up with GitHub
2. **New +** → **Web Service**
3. Connect this repo
4. Settings:
   - **Runtime:** Docker
   - **Name:** `invoiceagent-api` (your API URL will be `https://invoiceagent-api.onrender.com`)
   - **Plan:** Free
5. **Environment Variables** — add these:

| Key | Value |
|-----|-------|
| `JWT_SECRET` | any long random string |
| `REQUIRE_AUTH` | `true` |
| `ALLOWED_EMAIL_DOMAIN` | `fifthspace.com` |
| `COOKIE_SECURE` | `true` |
| `SERVE_FRONTEND` | `false` |
| `FRONTEND_URL` | `https://YOUR-APP.vercel.app` *(fill after Vercel — come back and update)* |
| `BACKEND_URL` | `https://invoiceagent-api.onrender.com` |
| `CORS_ORIGINS` | `https://YOUR-APP.vercel.app` *(fill after Vercel)* |
| `OPENAI_API_KEY` | your OpenAI key — **strongly recommended**, see note below |

6. Click **Create Web Service** → wait for deploy (~5–10 min)
7. Test: open `https://invoiceagent-api.onrender.com/api/health` → should say `{"status":"ok"}`

> **About `OPENAI_API_KEY`:** the billing-sheet-style invoice format (where the consultant
> already fills in a schedule-of-values table) parses fine without a key. But free-form T&M
> receipts (the "restaurant receipt" style invoices), the project chat, and the most reliable
> contract parsing all require an OpenAI key. Set one for production use.

---

## Part 2 — Frontend on Vercel (~3 min)

1. Go to [vercel.com](https://vercel.com) → sign up with GitHub
2. **Add New → Project**
3. Import this repo
4. Settings:
   - **Root Directory:** `frontend`
   - **Framework Preset:** Vite
5. **Environment Variables:**

| Key | Value |
|-----|-------|
| `VITE_API_URL` | `https://invoiceagent-api.onrender.com` |

6. Click **Deploy**
7. Copy your Vercel URL (e.g. `https://invoiceagent.vercel.app`)

---

## Part 3 — Connect them (~2 min)

Go back to **Render → your service → Environment** and update:

| Key | Value |
|-----|-------|
| `FRONTEND_URL` | your Vercel URL |
| `CORS_ORIGINS` | your Vercel URL |

Save → Render redeploys automatically.

---

## Part 4 — Use it

1. Open your **Vercel URL**
2. Click **First time? Create an account**
3. Register with `you@fifthspace.com` + password (8+ chars)
4. Create a project (e.g. "PPS — Albion Partners"), upload the contract, then upload invoices as
   they come in.

Nobody without a `@fifthspace.com` account can get in.

---

## Local dev

```bash
# .env in project root
JWT_SECRET=local-dev-secret
REQUIRE_AUTH=true
ALLOWED_EMAIL_DOMAIN=fifthspace.com
FRONTEND_URL=http://localhost:5173
BACKEND_URL=http://localhost:8000
CORS_ORIGINS=http://localhost:5173
OPENAI_API_KEY=sk-...

# Terminal 1
cd backend && python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Terminal 2
cd frontend && npm install && npm run dev
```

Open http://localhost:5173
