# PunchStart AI – Frontend Integration (Analyze → Results)

## Plan steps
- [ ] Update `frontend/assets/js/analyze.js` to collect all form values, call POST `/api/analyze`, show loading spinner, save response to `localStorage.startupReport`, and redirect to `results.html`.
- [ ] Update `frontend/assets/js/report.js` to read `startupReport` from `localStorage` and render all requested sections into cards (no dummy data).
- [ ] Update `frontend/pages/results.html` to be a premium responsive dashboard that only renders API response (inject via `report.js`).
- [ ] Verify navigation flow: Analyze page → results page renders correctly after API response.


