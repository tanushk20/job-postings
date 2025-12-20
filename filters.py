# filters.py

# ------------------
# SCORING WEIGHTS
# ------------------

TITLE_KEYWORD_SCORES = {
    # strong positives
    "machine learning": 5,
    "ml": 5,
    "ai": 5,
    "computational": 5,
    "bioinformatics": 3,
    "data scientist": 3,
    "research scientist": 3,
    "research engineer": 6,
    "Ops": 4,
    "software": 2,
    "data": 2,
    "member of technical staff": 4,
    "design": 2,
    "genAI": 4,
    "gen ai": 4,
    "gen-ai": 4,
    "generative ai": 4,
    "agentic ai": 4,
    # mild positives
    "engineer": 3,
    "scientist": 5,
    "computational biologist": 6,
    "computational biology": 6,
    "computational scientist": 5,
    "ml scientist": 5,
    "ai scientist": 5,
    "bio ml": 5,
    "deep learning": 5,
    "nlp": 4,
    "bioengineering": 3,
    "protein": 2,
    "therapeutics": 2,
    "drug discovery": 3,
    "genomics": 3,
    "single cell": 3,
    "transcriptomics": 2,
    "systems biology": 2,
}

TITLE_PENALTIES = {
    "intern": -10,
    "internship": -10,
    "manager": -10,
    "director": -10,
    "vp": -10,
    "principal": -10,
    "staff": -10,
    "qa": -10,
    "quality assurance": -10,
    "postdoctoral": -5,
    "postdoc": -5,
    "assistant professor": -8,
    "faculty": -8,
    "lecturer": -8,

}

LOCATION_SCORES = {
    "boston": 5,
    "cambridge": 5,
    "somerville": 5,
    "framingham": 5,
    "massachusetts": 5,
    "ma": 5,
    "san francisco": 4,
    "san jose": 4,
    "san mateo": 4,
    "mountain view": 4,
    "sunnyvale": 4,
    "palo alto": 4,
    "menlo park": 4,
    "redwood city": 4,
    "california": 4,
    "san diego": 3,
    "new york": 3,
    "nyc": 3,
    "toronto": 2,
    "vancouver": 2,
    "montreal": 2,
    "ottawa": 2,
    "washington dc": 2,
    "washington": 2,
    "new jersey": 2,
    "new jersey": 2,
    "seattle": 3,
    "remote": 1,
}

LOCATION_PENALTIES = {
    "india": -10,
    "china": -10,
    "bangalore": -10,
    "hyderabad": -10,
    "delhi": -10,
    "las vegas": -10,
    "nevada": -10,
}

REMOTE_BONUS = 0

# ------------------
# Helpers
# ------------------

def _norm(s: str | None) -> str:
    return s.lower() if s else ""

def score_title(title: str | None) -> int:
    t = _norm(title)
    score = 0

    for k, v in TITLE_KEYWORD_SCORES.items():
        if k in t:
            score += v

    for k, v in TITLE_PENALTIES.items():
        if k in t:
            score += v

    return score

def score_location(location: str | None) -> int:
    loc = _norm(location)
    score = 0

    for k, v in LOCATION_SCORES.items():
        if k in loc:
            score += v

    for k, v in LOCATION_PENALTIES.items():
        if k in loc:
            score += v

    if "remote" in loc:
        score += REMOTE_BONUS

    return score

def score_job(job: dict) -> int:
    return (
        score_title(job.get("title"))
        + score_location(job.get("location"))
    )
