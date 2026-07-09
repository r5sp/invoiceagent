# Deploy — one URL to send Joe

The whole app (website + API + login) runs as **one Render web service** at a single URL like
`https://invoiceagent.onrender.com`. No separate frontend host, no cross-domain setup. Login is
restricted to `@fifthspace.com` emails.

## Deploy on Render (~10 min, no GitHub connection needed)

1. Go to [render.com](https://render.com) → sign up / log in (free).
2. **New +** → **Web Service**.
3. Choose **"Public Git Repository"** and paste:
   `https://github.com/r5sp/invoiceagent`
   (Because the repo is public, you do NOT need to connect your GitHub account.)
4. Settings:
   - **Runtime:** Docker (auto-detected)
   - **Name:** `invoiceagent` → your URL becomes `https://invoiceagent.onrender.com`
   - **Plan:** Free
5. **Environment Variables** — add these:

| Key | Value |
|-----|-------|
| `JWT_SECRET` | any long random string (e.g. mash the keyboard for 40+ chars) |
| `REQUIRE_AUTH` | `true` |
| `ALLOWED_EMAIL_DOMAIN` | `fifthspace.com` |
| `COOKIE_SECURE` | `true` |
| `SERVE_FRONTEND` | `true` |
| `OPENAI_API_KEY` | your OpenAI key (recommended — see note) |

6. **Create Web Service** → wait for the first Docker build (~5–10 min).
7. Test: open `https://invoiceagent.onrender.com/api/health` → should say `{"status":"ok"}`.
8. Open `https://invoiceagent.onrender.com`, click **Create an account**, register with your
   `@fifthspace.com` email, and send Joe the same URL — he signs up with his `@fifthspace.com`
   email too. Nobody outside the domain can get in.

> **Fail-safe:** the app refuses to start if `REQUIRE_AUTH=true` and `JWT_SECRET` is left as the
> placeholder — so it can never accidentally go live with an open or forgeable login.

## Two things to know about the free tier

- **Cold start:** a free Render service sleeps after ~15 min idle; the first visit after that takes
  ~30–50 sec to wake up, then it's fast. Fine for a trial; upgrade to a paid instance ($7/mo) to
  keep it always-on.
- **Data resets on redeploy:** by default the app uses a SQLite file that is wiped whenever the
  service redeploys or restarts. For a quick trial that's fine. To keep data permanently, uncomment
  the `databases:` block in [render.yaml](render.yaml) (managed Postgres) and add the `DATABASE_URL`
  env var — the app already supports Postgres, no code change needed.

## About the OpenAI key

Contract parsing and the standard billing-sheet-format invoices work without a key. Free-form
"restaurant receipt" T&M invoices and the project chat need `OPENAI_API_KEY` set. Set one for the
full experience.

## Local dev

```bash
# backend
cd backend
python3.11 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
JWT_SECRET=local-dev-secret REQUIRE_AUTH=true ALLOWED_EMAIL_DOMAIN=fifthspace.com \
  uvicorn app.main:app --reload --port 8000

# frontend (separate terminal)
cd frontend && npm install && npm run dev
```

Open http://localhost:5173 (the dev server proxies `/api` to the backend on :8000).
