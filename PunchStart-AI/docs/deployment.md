# Deploying StartPunch on Vercel

The frontend (static files) and the API (Python serverless function) deploy together from this repository.

## 1. Project settings (one-time, in the Vercel dashboard)

| Setting | Value |
|---|---|
| **Root Directory** | `PunchStart-AI` (it was previously `PunchStart-AI/frontend`; it must now be the parent folder so `api/` and `backend/` are included) |
| Framework preset | Other |
| Build / output | taken from `PunchStart-AI/vercel.json` (output directory `frontend`, no build command) |
| Python | 3.12 (`PunchStart-AI/.python-version`) |
| Function max duration | 60 s (set in `vercel.json`; each pipeline stage is budgeted to finish in about 52 s) |

## 2. Environment variables (Production and Preview)

| Variable | Required | Notes |
|---|---|---|
| `DATABASE_URL` | **yes** | A Postgres connection string, e.g. a free Neon database from the Vercel Marketplace (it sets `DATABASE_URL` automatically). The app refuses to fall back to temporary storage on Vercel, so data is never silently lost. Tables are created automatically on first request. |
| `SESSION_SECRET` | **yes** | 32+ random characters, e.g. `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Changing it signs everyone out. |
| `GEMINI_API_KEY` | **yes** for AI features | Without it, reports still include retrieval and the rubric, but AI sections are marked unavailable. **The free tier allows about 20 `gemini-2.5-flash` requests per day per model**, which is roughly 2 full reports a day before the app falls back to lighter models. Real usage needs a paid Gemini tier. |
| `ADMIN_EMAILS` | optional | A comma-separated list of accounts that can use the moderation queue. |
| `GEMINI_MODEL`, `GEMINI_FALLBACK_MODELS`, `GEMINI_FAST_MODELS` | optional | Override model routing. |
| `DAILY_REPORT_QUOTA`, `DAILY_AI_QUOTA` | optional | Per-user daily limits (defaults: 8 reports, 120 other AI calls). |

## 3. Deploy
Push to the branch Vercel builds (`main` deploys to production; other branches get preview URLs). Then check:

- `GET /api/health` returns `"status": "ok"`, `"database": "ok"` and `"ai_configured": true`.
- The landing page shows live knowledge-base numbers.
- You can sign up, run an analysis, and see it on the workspace.

## Notes and limits
- **Knowledge base:** the snapshot ships with the code (`backend/data/kb`, ~8 MB) and loads into memory on each cold start, which takes about 1–2 s.
- **Rate limits** are per instance for bursts. AI quotas are enforced in the database across instances.
- **Images** are stored in Postgres (3 MB per image). Video is supported through YouTube, Vimeo and Loom links. For heavy media, move to object storage, e.g. Vercel Blob.
- **Hosting the API elsewhere** (Railway, Render, Fly): run `uvicorn startpunch.main:app` from `backend/` using `backend/requirements.txt`. Then set `CORS_ORIGINS` to the frontend origin and add `<meta name="startpunch-api" content="https://your-api-host">` to the pages.
