# StartPunch architecture

## Request flow

```
Browser (static pages, ES modules)
   │  same-origin fetch  /api/*   (HttpOnly session cookie + X-StartPunch-Client header)
   ▼
Vercel Python function  api/index.py  →  FastAPI app (startpunch.main)
   ├── security middleware: CSRF header check, rate limits, security headers, request IDs, JSON errors
   ├── routes/auth          accounts, sessions, password, export, deletion
   ├── routes/reports       analyses (staged pipeline), assistant, export, validation tracker, watchlist, compare
   ├── routes/intelligence  knowledge-base coverage, sectors, clusters, model cards, search
   └── routes/social        profiles, graph, posts, comments, feed, communities, startups, network, messages,
                            notifications, moderation, search, recommendations, AI helpers
        │
        ├── SQL database (SQLAlchemy Core: SQLite locally, Postgres in production)
        ├── Knowledge-base snapshot (files in backend/data/kb, loaded into memory per instance)
        ├── Trained models (backend/data/models, numpy inference)
        └── Gemini REST API (generation + embeddings) — server-side only
```

## Analysis pipeline (`analysis/pipeline.py`)

Each `POST /api/reports/{id}/advance` call runs exactly one stage and saves its output. That keeps every invocation short enough for serverless (each stage runs on a ~52-second budget) and lets an interrupted analysis resume. A database lease (`lock_until`) stops two requests from processing the same report.

| Stage | What happens |
|---|---|
| `understand` | The idea is embedded. The **industry** and **business-model** classifiers (TF-IDF+LR or embedding+LR) and the **cluster** model make their predictions. The LLM extracts structured signals; quotes must appear verbatim in the founder's text or they are discarded. Keyword heuristics are the fallback. |
| `research` | **Hybrid retrieval**: BM25 plus dense cosine search over chunk embeddings, combined with reciprocal-rank fusion. It uses metadata filters (sector, status, entity type, date, source), sector boosting and a boost for competitors the founder named, then aggregates results to company level. Verified shutdowns get a separate search. The **LLM grades relevance** of every candidate (direct / indirect / similar model / adjacent / unrelated) and unrelated candidates are dropped. Sources receive stable IDs (`S1…`). **Rubric scoring** runs here. |
| `write` | Five section groups (market, competition, business, build, risk) are generated in parallel with JSON-schema-constrained output. Only the evidence list may be cited. Failed groups are retried on the next call. |
| `synthesize` | The executive summary and final recommendations are written. **Validation** runs (below). Validation experiments are seeded into the tracker. |

### Response validation (`analysis/generate.py::validate`)
- Source IDs not in the evidence set are removed, both from `sources` and from inline `[S#]` markers.
- A point labeled `fact` must cite evidence. Every material number (currency, magnitude, %) and every evidence company name it mentions must appear in the cited snippets; otherwise the point is relabeled **`unverified`** and the reason is recorded.
- Metrics are never facts: market sizes, costs and projections are relabeled `estimate`.
- Sections the model didn't return are shown as *unavailable*, never filled with template text.

## Scoring (`analysis/scoring.py`)
The score is a transparent rule-based rubric with 13 weighted dimensions (weights sum to 100). Each dimension returns a score from 0–10, its rationale, evidence (with source IDs), its confidence (high when based on the founder's own words, medium when inferred, low for defaults), the information that's missing, and the cheapest next validation step. There is no outcome data, so it is not presented as a prediction.

## Knowledge base (`ingest/`)

**Sources.** Everything comes from the public Hacker News Search API:
- Launch HN posts.
- Show HN posts with at least 100 points.
- Shutdown and post-mortem posts.

Each record keeps a link to its original thread. Wikimedia sources were evaluated and deliberately excluded: they require contact details in the User-Agent, which the project owner chose not to share.

**Build pipeline steps:**
1. Fetch (with a cache).
2. Verify shutdown candidates with an LLM. Outage, security and conference post-mortems are rejected.
3. Clean and validate records (dates, names, minimum text).
4. Resolve entities by domain and by normalized name, with a strict domain check for shutdown stories hosted on third-party blogs.
5. Chunk text along sentence boundaries, with overlap.
6. Embed chunks (`gemini-embedding-001`, 256 dimensions, float16), throttled and resumable.
7. Assign LLM silver labels to a sample.
8. Train and evaluate the classifiers, then use them to classify the remaining entities (only when probability is at least 0.40).
9. Cluster with k-means, choosing k by silhouette score, and describe clusters with c-TF-IDF terms.
10. Compute sector statistics.
11. Run the retrieval evaluation.
12. Write a versioned snapshot plus `manifest.json` (sources, licenses, fetch dates, counts, build report, metrics).

**Freshness.** The manifest records the build date, and the Market intelligence page flags the snapshot as stale after 30 days. A manual GitHub Actions workflow (`kb-refresh.yml`) rebuilds the snapshot and uploads it as an artifact for review.

## ML components (`ml/`)
| Model | Inputs → outputs | Training data | Evaluation |
|---|---|---|---|
| Industry classifier | description text or embedding → probabilities over 22 sectors | LLM silver labels on a stratified sample | 80/20 hold-out: accuracy, macro-F1, per-class F1, majority baseline (stored in model card) |
| Business-model classifier | same → 10 business models | same | same |
| Market clusters | entity embeddings → cluster id | all embedded entities | silhouette by k; cluster terms |
| Retrieval | queries → ranked entities | — | known-item recall@10, sector precision@10 for lexical / dense / hybrid |

The models are trained with scikit-learn and exported as JSON/NPZ. Production inference re-implements TF-IDF and logistic regression in numpy; `tests/test_retrieval_ml.py` checks the numpy output matches scikit-learn.

## Security & privacy
- Passwords are hashed with scrypt.
- Sessions are HS256 JWTs in an `HttpOnly` cookie (`Secure` in production, `SameSite=Lax`), carrying a token version so you can sign out everywhere.
- CSRF protection: every unsafe request must carry the `X-StartPunch-Client` header, which other sites can't send without a CORS preflight, and CORS is closed by default.
- Rate limits: in-memory bursts, plus durable daily quotas for AI features stored in the `ai_usage` table.
- Uploaded images are validated by their file signature (magic bytes) and served with a restrictive CSP.
- Pages have a strict Content-Security-Policy (`script-src 'self'`; no inline scripts).
- Reports are visible only to their owner; publishing shares only the fields the founder ticks.
- Privacy controls cover profile visibility, message policy, blocking, data export and account deletion.
- Secrets live only in environment variables. The Gemini key is never sent to the browser.
