from twinquery.agents.planner import classify_intent


def test_planner_classifies_structured_query() -> None:
    assert classify_intent("Which buildings have the highest energy intensity?") == "structured_data_query"


def test_planner_classifies_document_query() -> None:
    assert classify_intent("What does the retrofit guide say about air sealing?") == "document_policy_query"


def test_planner_classifies_hybrid_query() -> None:
    assert classify_intent("Which buildings should be retrofitted and why?") == "hybrid_query"


def test_planner_classifies_unsupported_query() -> None:
    assert classify_intent("Send an email to the building owner") == "unsupported"


def test_planner_classifies_hybrid_boundary() -> None:
    # Combines data terms (oldest) and doc terms (guidance)
    assert classify_intent("Which buildings are oldest and what retrofit guidance applies?") == "hybrid_query"


def test_planner_classifies_pure_map() -> None:
    # Data terms only
    assert classify_intent("Show me the oldest buildings on the map") == "structured_data_query"


def test_planner_classifies_pure_guidance() -> None:
    # Doc terms only
    assert classify_intent("What is the retrofit guidance for old buildings?") == "document_policy_query"


def test_planner_routes_energy_intensity_ranking_to_structured() -> None:
    # Pure ranking question: building rows answer this, not RAG.
    assert (
        classify_intent("Which buildings have the highest energy intensity?")
        == "structured_data_query"
    )


def test_planner_routes_high_energy_with_retrofit_explanation_to_hybrid() -> None:
    assert (
        classify_intent("Show high energy buildings and explain retrofit options")
        == "hybrid_query"
    )


def test_planner_routes_retrofit_measures_question_to_documents() -> None:
    assert (
        classify_intent("What retrofit measures help older buildings?")
        == "document_policy_query"
    )


def test_planner_routes_lowest_energy_ranking_to_structured() -> None:
    assert (
        classify_intent("List the buildings with the lowest energy intensity")
        == "structured_data_query"
    )


def test_planner_routes_recommended_hvac_demo_to_hybrid() -> None:
    # Primary demo question per README.
    question = (
        "Show me the buildings with the highest energy intensity and "
        "explain the recommended HVAC retrofits based on local guidance."
    )
    assert classify_intent(question) == "hybrid_query"

