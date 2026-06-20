# PunchStart API

## Health

`GET /health`

Returns service status.

## Analyze Startup

`POST /api/analyze`

Request:

```json
{
  "startup_name": "Atlas Ledger",
  "industry": "Fintech",
  "problem": "SME exporters lack real-time cash visibility.",
  "solution": "A finance dashboard for invoices, FX, and working capital.",
  "target_customers": "SME exporters",
  "revenue_model": "SaaS Subscription",
  "team_size": "3",
  "funding_requirement": "INR 75,00,000",
  "business_stage": "MVP Development"
}
```

Response:

Returns a complete investor-grade report with:

- `executive_summary`
- `startup_score`
- `investor_readiness_score`
- `tam_sam_som`
- `market_analysis`
- `competitor_landscape`
- `customer_persona`
- `revenue_strategy`
- `business_model_analysis`
- `swot`
- `porters_five_forces`
- `risk_matrix`
- `funding_recommendation`
- `mvp_roadmap`
- `go_to_market_strategy`
- `growth_strategy`
- `pitch_deck_outline`
- `founder_recommendations`
- compatibility aliases for older frontend consumers
