"""Deterministic planner for TwinQuery question routing."""

from __future__ import annotations

from twinquery.agents.state import Intent


STRONG_DATA_PHRASES: tuple[str, ...] = (
    "which buildings",
    "which building",
    "show me",
    "show high",
    "show top",
    "show buildings",
    "show residential",
    "show municipal",
    "show schools",
    "list buildings",
    "list the buildings",
    "map the",
    "on the map",
    "highest",
    "lowest",
    "top ",
    "bottom ",
    "rank",
    "ranked",
    "ranking",
    "near downtown",
    "near ",
    "within ",
    "built before",
    "built after",
    "retrofit priority",
    "retrofit score",
    "energy intensity",
    "highest energy",
    "lowest energy",
    "high energy",
    "low energy",
    "tallest",
    "shortest",
    "oldest",
    "newest",
    "above 75",
    "above 80",
    "above 90",
    "kwh/m2",
)

STRONG_DOC_PHRASES: tuple[str, ...] = (
    "what guidance",
    "what is the guidance",
    "what does the guidance",
    "what is the retrofit guidance",
    "what retrofit guidance",
    "what retrofit measures",
    "what retrofit options",
    "what measures",
    "retrofit options",
    "retrofit measures",
    "recommended measures",
    "recommended retrofits",
    "recommended hvac",
    "recommend retrofits",
    "explain",
    "explanation",
    "guidance",
    "policy",
    "guide says",
    "guide say",
    "say about",
    "what does the",
    "why",
    "advice",
    "recommend",
    "recommendation",
    "best practice",
    "rationale",
)

DATA_TERMS: frozenset[str] = frozenset(
    {
        "average",
        "benchmark",
        "buildings",
        "built",
        "city",
        "distance",
        "emissions",
        "energy",
        "intensity",
        "near",
        "payback",
        "priority",
        "radius",
        "score",
        "within",
        "kwh",
        "polygon",
    }
)

DOC_TERMS: frozenset[str] = frozenset(
    {
        "document",
        "guide",
        "guidance",
        "notes",
        "policy",
        "recommend",
        "recommendation",
        "say",
        "why",
        "explain",
    }
)

UNSUPPORTED_TERMS: frozenset[str] = frozenset(
    {
        "email",
        "forecast stock",
        "login",
        "password",
        "price bitcoin",
        "send an email",
        "send a message",
        "weather tomorrow",
    }
)


def _matches_any(text: str, phrases) -> bool:
    return any(phrase in text for phrase in phrases)


def classify_intent(question: str) -> Intent:
    text = question.strip().lower()
    if not text:
        return "unsupported"
    if _matches_any(text, UNSUPPORTED_TERMS):
        return "unsupported"

    strong_data = _matches_any(text, STRONG_DATA_PHRASES)
    strong_doc = _matches_any(text, STRONG_DOC_PHRASES)

    if strong_data and strong_doc:
        return "hybrid_query"
    if strong_doc:
        return "document_policy_query"
    if strong_data:
        return "structured_data_query"

    weak_data = _matches_any(text, DATA_TERMS)
    weak_doc = _matches_any(text, DOC_TERMS)

    if weak_data and weak_doc:
        return "hybrid_query"
    if weak_doc:
        return "document_policy_query"
    if weak_data:
        return "structured_data_query"
    return "unsupported"


def build_plan(question: str) -> tuple[Intent, list[str]]:
    intent = classify_intent(question)
    plans = {
        "structured_data_query": [
            "Generate read-only SQL for the building-stock database.",
            "Validate SQL guardrails.",
            "Execute safe SQL.",
            "Summarize the database rows as the primary answer.",
        ],
        "document_policy_query": [
            "Retrieve local retrofit guidance documents.",
            "Synthesize a concise answer grounded in document context.",
        ],
        "hybrid_query": [
            "Generate and validate read-only SQL.",
            "Execute safe SQL against the building stock as the source of truth for selected buildings.",
            "Retrieve local retrofit guidance documents for explanation only.",
            "Lead the answer with database rows and use guidance as supporting explanation.",
        ],
        "unsupported": [
            "Refuse unsupported request and explain available TwinQuery capabilities.",
        ],
    }
    return intent, plans[intent]


def plan_question(question: str) -> list[str]:
    return build_plan(question)[1]
