# StartPunch — remaining work

## Needs the project owner (credentials / settings)
- [ ] Vercel: change **Root Directory** to `PunchStart-AI` and add `DATABASE_URL`, `SESSION_SECRET`, `GEMINI_API_KEY` (see `PunchStart-AI/docs/deployment.md`).
- [ ] Gemini: move to a paid tier. The free tier allows ~20 `gemini-2.5-flash` requests/day and ~1,000 embedding inputs/day, so reports fall back to lighter models and the semantic index fills slowly.
- [ ] Re-run `python -m startpunch.ingest build` (locally, or via the manual *Knowledge-base refresh* workflow with a `GEMINI_API_KEY` secret) until every chunk has an embedding. The build resumes where it stopped; check coverage on the Market intelligence page.
- [ ] Optional: set `ADMIN_EMAILS` to enable the moderation queue.

## Data & intelligence
- [ ] Add more licensed sources (e.g. Crunchbase/PitchBook/Dealroom via paid API keys, SEC EDGAR, Companies House) for funding rounds, financials and non-HN companies. Wikimedia was skipped by decision; it needs contact details in the User-Agent.
- [ ] Human-label a gold set (~300 entities) to measure classifier accuracy against ground truth, not just against LLM silver labels.
- [ ] Add an LLM-judged relevance evaluation for realistic idea queries (precision@10 per retrieval mode).
- [ ] Add a live news source (e.g. GDELT) for "recent market developments".
- [ ] Move to a database-backed vector index (pgvector) if the corpus outgrows in-memory loading.

## Product
- [ ] Email notifications and password reset (needs an email provider).
- [ ] Object storage for media (Vercel Blob/S3) instead of Postgres for large uploads; native video upload.
- [ ] Real-time messaging (currently polls every 8 s).
- [ ] Shared, cross-instance rate-limit store (e.g. Redis) for burst limits; AI quotas are already database-backed.
- [ ] Schema migrations tooling (Alembic) once the schema starts changing.
- [ ] Postgres integration test in CI (current tests use SQLite; the pg8000 path is configured but has not been exercised against a live Postgres).
