def calculate_score_fallback(startup_data: dict) -> int:
    """
    Heuristic scoring when the primary analysis engine is unavailable.
    Weights: industry potential (40%), problem clarity (20%),
    revenue model existence (20%), team size (10%), funding planning (10%).
    Returns an integer between 0 and 100.
    """
    score = 0

    # 1. Industry potential (0–40)
    industry_potential = {
        "Intelligent Automation": 95, "AI/ML": 95, "Fintech": 90, "Healthtech": 85, "EV": 90,
        "CleanTech": 85, "SaaS": 85, "Edtech": 80, "AgriTech": 75,
        "Logistics": 70, "E-commerce": 75, "Foodtech": 65, "PropTech": 65
    }
    industry = startup_data.get("industry", "").strip()
    ind_score = industry_potential.get(industry, 60)
    score += int(ind_score * 0.4)

    # 2. Problem clarity (0–20) – longer description hints at deeper thought
    problem_len = len(startup_data.get("problem", ""))
    problem_score = min(20, problem_len // 10)  # up to 20
    score += problem_score

    # 3. Revenue model defined (0–20)
    if startup_data.get("revenue_model", "").strip():
        score += 20

    # 4. Team size (0–10)
    try:
        team_size = int(startup_data.get("team_size", 0))
    except (ValueError, TypeError):
        team_size = 0
    team_score = min(10, team_size * 3)
    score += team_score

    # 5. Funding requirement specified (0–10)
    if startup_data.get("funding_requirement", "").strip():
        score += 10

    return min(score, 100)


def detailed_score_from_analysis(analysis_data: dict) -> int:
    """
    Placeholder for future ML/dataset-based scoring.
    Currently returns the generated score directly.
    """
    return analysis_data.get("startup_score", 0)
