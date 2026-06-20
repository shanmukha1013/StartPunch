import logging
from textwrap import dedent

from services.gemini_service import generate_content
from services.report_generator import generate_report_json, normalize_report


logger = logging.getLogger("punchstart.analyzer")


async def analyze_startup(data: dict) -> dict:
    prompt = _build_prompt(data)
    try:
        model_response = await generate_content(prompt)
        return generate_report_json(model_response, data)
    except Exception:
        logger.exception("Primary analysis path recovered with deterministic report generation")
        return normalize_report(None, data)


def _build_prompt(data: dict) -> str:
    return dedent(
        f"""
        You are a top-tier Venture Partner, Senior Startup Consultant, and VC Growth Strategist.
        Return one strict JSON object only. Do not wrap in markdown tags or add comments.
        
        Write in a sharp, analytical, and professional tone that balances investment risk assessment with strategic company building.
        Avoid robotic or generic AI filler phrases (e.g., "in conclusion", "it is important to note", "as an AI", "revolutionize the industry", "game-changing solution").
        Focus on customer discovery signals, distribution advantages, unit economics, regulatory factors in the Indian market, regulatory compliance, and concrete operational milestones.

        CRITICAL WRITING INSTRUCTION: SWOT strengths, weaknesses, opportunities, threats, and founder_recommendations must be brief, crisp, and high-readability bullets. Each bullet must be a single, short sentence of maximum 12-15 words. No long paragraphs. Provide exactly 3 bullet points per SWOT category and exactly 4 items for founder_recommendations.

        Analyze this startup for the Indian startup ecosystem:
        startup_name: {_value(data, "startup_name")}
        industry: {_value(data, "industry")}
        problem: {_value(data, "problem")}
        solution: {_value(data, "solution")}
        target_customers: {_value(data, "target_customers")}
        revenue_model: {_value(data, "revenue_model")}
        team_size: {_value(data, "team_size")}
        funding_requirement: {_value(data, "funding_requirement")}
        business_stage: {_value(data, "business_stage")}

        Required JSON schema:
        {{
          "executive_summary": "2-4 professional, data-driven sentences summarizing the core value proposition, beachhead wedge, and strategic validation pathway.",
          "startup_score": 0-100 integer representing viability,
          "investor_readiness_score": 0-100 integer representing fundability,
          "tam_sam_som": {{
            "tam": "INR value (e.g. 'INR 45,000 Cr') and specific industry segment definition",
            "sam": "INR value (e.g. 'INR 9,000 Cr') and reachable segment definition",
            "som": "INR value (e.g. 'INR 450 Cr') and target 3-5 year beachhead share",
            "rationale": "Sizing assumptions, digital buyer penetrations, and sector growth indicators."
          }},
          "market_analysis": "Detailed, professional market analysis outlining tailwinds, structural challenges, and beachhead segments.",
          "industry_trends": ["First major macro or tech trend", "Second major user behavior trend", "Third trend regarding distribution or credit in India"],
          "competitor_landscape": [
            {{"name": "Specific incumbent category", "positioning": "How they position", "advantage": "Their distribution or relationship moat", "gap_to_exploit": "Vulnerability or workflow gap this startup can exploit"}}
          ],
          "customer_persona": "Specific profile of first target digital buyer: title, pain point, and onboarding motivation.",
          "revenue_strategy": "SaaS model, tiered pricing, or transactional take-rate outline with monetizable milestones.",
          "business_model_analysis": "Gross margin targets, customer acquisition loops, and payback period assumptions.",
          "swot": {{
            "strengths": ["Concise advantage 1 (max 12 words)", "Concise advantage 2 (max 12 words)", "Concise advantage 3 (max 12 words)"],
            "weaknesses": ["Concise risk 1 (max 12 words)", "Concise risk 2 (max 12 words)", "Concise risk 3 (max 12 words)"],
            "opportunities": ["Concise expansion 1 (max 12 words)", "Concise expansion 2 (max 12 words)", "Concise expansion 3 (max 12 words)"],
            "threats": ["Concise threat 1 (max 12 words)", "Concise threat 2 (max 12 words)", "Concise threat 3 (max 12 words)"]
          }},
          "porters_five_forces": [
            {{"force": "Competitive rivalry", "rating": "Low/Medium/High", "insight": "Competitive concentration and pricing pressure details"}},
            {{"force": "Threat of new entrants", "rating": "Low/Medium/High", "insight": "Capital requirements, automation ease, and onboarding friction details"}},
            {{"force": "Buyer power", "rating": "Low/Medium/High", "insight": "Customer concentration and willingness to switch details"}},
            {{"force": "Supplier power", "rating": "Low/Medium/High", "insight": "Cloud, model, or API vendor concentration details"}},
            {{"force": "Threat of substitutes", "rating": "Low/Medium/High", "insight": "Spreadsheet usage or manual outsourcing alternatives details"}}
          ],
          "go_to_market_strategy": "Concrete customer acquisition steps, target outbound channels, and weekly activation metrics.",
          "risk_matrix": [
            {{"risk": "Specific high-risk operational assumption", "severity": "Low/Medium/High", "likelihood": "Low/Medium/High", "mitigation": "Clear tactical mitigation action"}}
          ],
          "funding_recommendation": "Amount in INR, stage-appropriate milestone gating, and use-of-funds roadmap.",
          "mvp_roadmap": [
            {{"phase": "Phase 1: Discovery & Wedge", "timeline": "Weeks 1-4", "focus": "ICP definitions and initial user interviews", "success_metric": "X design partners secured"}},
            {{"phase": "Phase 2: Concierge / Alpha", "timeline": "Weeks 5-8", "focus": "Manual delivery of core workflow outcome", "success_metric": "X paid pilots booked"}},
            {{"phase": "Phase 3: Automated Beta", "timeline": "Weeks 9-12", "focus": "Self-serve workflow automation release", "success_metric": "X% weekly retention rate"}}
          ],
          "growth_strategy": "Moat expansion pathway, integrations, and channel partner strategy.",
          "pitch_deck_outline": [
            {{"title": "Slide Title", "content": "Clear slide content and visual recommendation"}}
          ],
          "market_timing_analysis": "Why now is the right windows for this model relative to macro shifts and technology rails.",
          "founder_recommendations": [
            "Actionable recommendation 1 (e.g. IC validation criteria)",
            "Actionable recommendation 2 (e.g. pilot pricing rules)",
            "Actionable recommendation 3 (e.g. analytics setup)",
            "Actionable recommendation 4 (e.g. distribution lock-in)"
          ],
          "monetization_strategy": "Pricing strategy, upsells, and monetization cycles.",
          "investor_attractiveness_analysis": "VC funding viability, criteria for seed rounds, and the must-prove milestones."
        }}
        """
    ).strip()


def _value(data: dict, key: str) -> str:
    value = data.get(key)
    return str(value).strip() if value is not None and str(value).strip() else "Not specified by founder"
