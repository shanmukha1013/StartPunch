"""Sector taxonomy and deterministic mapping from raw industry labels.

Wikidata ``industry`` (P452) labels are heterogeneous ("financial services",
"video game industry", "software industry"...). We map them to a compact startup
sector taxonomy with transparent keyword rules. Generic labels such as
"software industry" or "internet" are mapped with low priority so that a more
specific label (e.g. "payment") wins.
"""
from __future__ import annotations

import re

SECTORS: dict[str, str] = {
    "ai_ml": "AI & Machine Learning",
    "devtools": "Developer Tools & Infrastructure",
    "enterprise_saas": "Enterprise Software & SaaS",
    "fintech": "FinTech",
    "crypto_web3": "Crypto & Web3",
    "healthtech": "HealthTech & Biotech",
    "edtech": "EdTech",
    "ecommerce": "E-commerce & Retail",
    "media_content": "Media & Content",
    "social_communication": "Social & Communication",
    "gaming": "Gaming",
    "mobility": "Mobility & Transportation",
    "logistics": "Logistics & Supply Chain",
    "cleantech": "CleanTech & Energy",
    "food_agri": "FoodTech & AgriTech",
    "proptech": "PropTech & Real Estate",
    "travel": "Travel & Hospitality",
    "hr_work": "HR & Future of Work",
    "cybersecurity": "Cybersecurity",
    "hardware_iot": "Hardware, Robotics & IoT",
    "telecom": "Telecommunications",
    "space_defense": "Aerospace & Space",
}

# (sector, priority, pattern). Higher priority wins when several labels match.
_RULES: list[tuple[str, int, str]] = [
    ("ai_ml", 9, r"artificial intelligence|machine learning|deep learning|computer vision|natural language|generative ai|\bai\b|\bllm\b|chatbot|neural"),
    ("cybersecurity", 9, r"computer security|cyber ?security|information security|network security|antivirus|identity management|\bfraud\b"),
    ("crypto_web3", 9, r"cryptocurrenc|blockchain|bitcoin|ethereum|\bnft\b|\bweb3\b|decentrali[sz]ed finance|\bdefi\b|crypto exchange"),
    ("fintech", 8, r"financ|payment|bank|lending|loan|credit|insurance|insurtech|fintech|invest|brokerage|wealth|accounting|money transfer|remittance|stock exchange|trading|mortgage|neobank"),
    ("healthtech", 8, r"health|medic|pharma|biotech|biotechnolog|clinic|hospital|diagnos|genom|life science|telemedicine|dental|mental health|wellness|fitness|drug"),
    ("edtech", 8, r"education|edtech|e-learning|learning|tutor|school|universit|online course|mooc"),
    ("gaming", 8, r"video game|game develop|gaming|esports|\bgames?\b|game publish"),
    ("food_agri", 8, r"\bfood|restaurant|grocery|meal|beverage|agricultur|agritech|farming|\bfarm|catering|delivery of food"),
    ("proptech", 8, r"real estate|property|proptech|housing|construction|home rental|mortgage broker|co-?working"),
    ("travel", 8, r"travel|tourism|hospitality|hotel|airline|vacation|booking"),
    ("mobility", 8, r"ride-?shar|ride-?hail|car shar|electric vehicle|automotive|vehicle|scooter|bicycle shar|transport|mobility|autonomous driving|taxi"),
    ("logistics", 8, r"logistic|supply chain|freight|shipping|courier|parcel|warehous|delivery service|last[- ]mile|trucking"),
    ("cleantech", 8, r"renewable|solar|wind power|clean ?tech|energy storage|battery|electric power|energy|climate|carbon|sustainab|recycling|waste management|water treatment"),
    ("space_defense", 8, r"aerospace|spaceflight|satellite|space industry|rocket|launch vehicle|defen[cs]e industry|aviation|drone"),
    ("hr_work", 7, r"human resources|recruit|staffing|employment|job search|payroll|freelanc|workforce|talent"),
    ("social_communication", 7, r"social network|social media|messaging|instant messag|dating|online community|communication|video conferenc|voice over ip|\bvoip\b|email"),
    ("media_content", 7, r"\bmedia\b|publishing|news|journalism|music|streaming|film|video|podcast|entertainment|broadcast|advertising|marketing|content|photograph|creator"),
    ("ecommerce", 7, r"e-?commerce|online shop|retail|marketplace|online auction|fashion|apparel|consumer goods|cosmetic|direct-to-consumer|\bd2c\b|wholesale|subscription box"),
    ("hardware_iot", 7, r"hardware|semiconductor|electronics|robot|internet of things|\biot\b|3d printing|consumer electronics|computer hardware|wearable|sensor|manufactur"),
    ("telecom", 7, r"telecommunicat|mobile network|internet service provider|wireless|broadband|\b5g\b|telecom"),
    ("devtools", 6, r"developer tool|software development|cloud computing|web hosting|data storage|database|devops|open source|programming|api\b|infrastructure as a service|platform as a service|data center|web service|content delivery"),
    ("enterprise_saas", 4, r"enterprise software|business software|software as a service|\bsaas\b|customer relationship|\bcrm\b|productivity software|collaboration software|analytics|business intelligence|project management|consulting|information technology|it service|software industry|software|computer"),
]
_COMPILED = [(sector, priority, re.compile(pattern, re.IGNORECASE)) for sector, priority, pattern in _RULES]

# Labels too generic to assign a sector on their own.
GENERIC = re.compile(r"^(internet|internet industry|online service|technology|technology industry|high tech|information industry|conglomerate|holding company|e-business)$", re.I)


def map_industries(labels: list[str]) -> str | None:
    """Return the best sector key for a list of raw industry labels, or None."""
    best: tuple[int, int, str] | None = None
    for position, label in enumerate(labels):
        label = (label or "").strip()
        if not label or GENERIC.match(label):
            continue
        for sector, priority, regex in _COMPILED:
            if regex.search(label):
                key = (priority, -position, sector)
                if best is None or key > best:
                    best = key
                break  # first (most specific) rule per label
    return best[2] if best else None


def sector_label(key: str | None) -> str:
    return SECTORS.get(key or "", "Other")


def guess_sector_from_text(text: str) -> tuple[str | None, list[str]]:
    """Keyword fallback used only when the trained classifier is unavailable."""
    hits: dict[str, int] = {}
    for sector, priority, regex in _COMPILED:
        count = len(regex.findall(text or ""))
        if count:
            hits[sector] = hits.get(sector, 0) + count * priority
    ranked = sorted(hits, key=hits.get, reverse=True)
    return (ranked[0] if ranked else None), ranked[:3]
