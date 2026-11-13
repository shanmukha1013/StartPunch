<div align="center">

# StartPunch

### Discover ideas · Validate opportunities · Connect with people · Build real businesses

An AI-powered startup intelligence platform and professional network for founders, builders and investors.

**Live:** https://start-punch.vercel.app

</div>

---

## What it does

**1. Startup intelligence.** Describe any idea. StartPunch:

1. Asks follow-up questions about whatever is missing.
2. Classifies the idea by sector and business model with trained models.
3. Searches a knowledge base of real product launches and verified shutdowns, using BM25 plus semantic embeddings fused together.
4. Asks an LLM to grade every match as a direct competitor, indirect competitor, similar model, adjacent, or unrelated.
5. Scores the idea with a transparent 13-dimension rubric.
6. Writes a 35-section report from that evidence only.

Every statement in the report is labeled **fact · founder input · estimate · assumption · recommendation**. Citations are checked automatically. A "fact" whose numbers or company names don't appear in the cited source is relabeled **unverified**.

**2. Founder network.** The network includes:

- Profiles, follows, and connections.
- A feed with ranking and trending.
- Posts with images, links and video, plus likes, threaded comments, reposts and bookmarks.
- 12 topic communities.
- Public startup pages with collaboration requests.
- Direct messages and notifications.
- Blocking, reporting and moderation.
- Recommendations for people and communities that explain why each match was made.
- AI helpers that improve a post before you publish it and summarize long discussions.

**3. Founder workspace.** Your workspace holds:

- Your private reports.
- An AI founder assistant that answers questions grounded in each report.
- A validation-experiment tracker.
- A competitor watchlist.
- Side-by-side report comparison.
- Markdown, JSON and PDF export.
- Publishing a summary you choose, never the full report.

## What it does *not* claim

- **The score is not a prediction of success.** It is a rule-based rubric, and each dimension shows its reasoning, evidence and confidence.
- **Coverage is limited to public Hacker News posts.** The knowledge base is built from Launch HN, Show HN (100+ points) and verified shutdown and post-mortem posts. It is tech-heavy and skewed toward US and YC companies. The Market intelligence page shows exact coverage, freshness, model metrics and known limitations.
- **Market sizes and costs are labeled estimates.** They come with their assumptions, not invented "facts".
- **Classifier metrics measure agreement with LLM-assigned labels**, not human ground truth.

## Architecture

```
PunchStart-AI/
├── api/index.py            Vercel Python function → FastAPI app (all /api/* routes)
├── vercel.json             static frontend + function config + security headers
├── requirements.txt        runtime dependencies (no SDK bloat, numpy-only ML inference)
├── frontend/               static multi-page app (vanilla ES modules, no build step)
│   ├── index.html          landing
│   ├── pages/*.html        workspace, analysis, report, feed, explore, profiles, …
│   └── assets/{css,js}     design system, shell, components, page modules
└── backend/
    ├── startpunch/
    │   ├── main.py         app factory, CSRF/security middleware, error handling
    │   ├── config.py db.py security.py ratelimit.py llm.py
    │   ├── analysis/       signals → research (RAG) → scoring → generation → validation, assistant
    │   ├── kb/             knowledge-base store, BM25, hybrid retrieval (RRF, filters, rerank)
    │   ├── ml/             numpy inference for trained classifiers & clusters; offline training
    │   ├── ingest/         source connectors, cleaning, entity resolution, chunking, build pipeline
    │   └── routes/         auth, reports, intelligence, social
    ├── data/kb/            versioned knowledge-base snapshot (+ manifest with sources & licenses)
    ├── data/models/        versioned models with model cards (metrics, data, limitations)
    └── tests/              pytest suite (API, social, retrieval, ML parity, pipeline, validation)
```

See [`PunchStart-AI/docs/architecture.md`](PunchStart-AI/docs/architecture.md) and [`PunchStart-AI/docs/deployment.md`](PunchStart-AI/docs/deployment.md).

**Stack:**

- **Backend:** FastAPI, SQLAlchemy Core (SQLite locally, Postgres in production via pure-Python `pg8000`), PyJWT sessions in HttpOnly cookies, scrypt password hashing.
- **AI:** Google Gemini REST API for generation and embeddings, with task-based model routing and quota-aware fallback.
- **ML:** scikit-learn for offline training only; inference is numpy.
- **Frontend:** vanilla JS, served as static files on Vercel.

## Run locally

```bash
cd PunchStart-AI/backend
python -m venv .venv && . .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env                                # add your GEMINI_API_KEY
uvicorn startpunch.main:app --reload --port 8000    # API + frontend on http://localhost:8000
python -m pytest                                    # test suite
```

To rebuild the knowledge base and retrain the models (this needs scikit-learn and Gemini quota; it resumes where it stopped):

```bash
pip install -r requirements-ml.txt
python -m startpunch.ingest build          # add --refresh to re-fetch sources
python -m startpunch.ingest evaluate       # retrieval evaluation → manifest
```

## Deployment

The frontend and API deploy together on Vercel: the frontend as static files, and `api/index.py` as a Python serverless function. Production needs these environment variables:

- `DATABASE_URL` (Postgres)
- `SESSION_SECRET`
- `GEMINI_API_KEY`
- Optionally `ADMIN_EMAILS`

The Vercel project's **Root Directory must be `PunchStart-AI`**. Details are in [`docs/deployment.md`](PunchStart-AI/docs/deployment.md).

## Connect

**Portfolio:** https://shanmukha-portfolio-six.vercel.app · **LinkedIn:** https://linkedin.com/in/marellashanmukhareddy
