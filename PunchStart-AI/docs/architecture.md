# PunchStart Architecture

PunchStart is a startup intelligence platform with a static frontend and FastAPI backend.

## Frontend

- `frontend/index.html`: landing page and demo-report entry.
- `frontend/pages/analyze.html`: multi-step validation wizard with autosave and loading pipeline.
- `frontend/pages/results.html`: investor report dashboard with notes, bookmarks, export, share, and animated metrics.
- `frontend/pages/dashboard.html`: Founder Command Center with analytics, comparison, health meter, and recommendations.
- `frontend/pages/feed.html`: founder insight feed backed by local storage.
- `frontend/assets/js/common.js`: global command palette and shared navigation actions.

## Backend

- `backend/app.py`: FastAPI application, CORS, health route, and router registration.
- `backend/routes/analyze.py`: validates the startup payload and returns the report contract.
- `backend/services/startup_analyzer.py`: builds the strict analysis prompt and coordinates report generation.
- `backend/services/gemini_service.py`: resilient structured generation with model selection, retries, timeouts, and safe recovery.
- `backend/services/report_generator.py`: JSON repair, schema validation, compatibility fields, and deterministic professional report generation.
- `backend/services/dataset_engine.py`: CSV benchmark loading utilities.

## Report Contract

Reports include scores, market sizing, market analysis, competitor matrix, customer persona, revenue analysis, SWOT, Porter's Five Forces, risk heatmap, funding strategy, roadmap, pitch deck outline, recommendations, and investor attractiveness analysis.
