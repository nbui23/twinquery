from twinquery.agents.synthesizer import synthesize_agent_answer


def test_synthesis_with_rows_and_empty_rag_answers_from_rows() -> None:
    rows = [
        {"name": "Building A", "estimated_energy_intensity_kwh_m2": 420.5},
        {"name": "Building B", "estimated_energy_intensity_kwh_m2": 410.0},
    ]
    answer = synthesize_agent_answer(
        question="Which buildings have the highest energy intensity?",
        intent="structured_data_query",
        generated_sql="SELECT name FROM buildings ORDER BY estimated_energy_intensity_kwh_m2 DESC",
        sql_valid=True,
        validation_message="ok",
        rows=rows,
        rag_context=[],
        errors=[],
    )

    assert "Database results (primary answer):" in answer
    assert "Building A" in answer
    assert "Building B" in answer
    # Must not claim docs lack information when DB rows answered the question.
    assert "Local documents do not contain enough information" not in answer
    assert "synthetic database rows" in answer


def test_synthesis_hybrid_leads_with_rows_then_guidance() -> None:
    rows = [{"name": "Office Tower", "retrofit_priority_score": 88}]
    rag_context = [
        {"source": "retrofit_guidelines.md", "section": "HVAC", "text": "Consider heat pumps."}
    ]
    answer = synthesize_agent_answer(
        question="Which buildings need retrofits and why?",
        intent="hybrid_query",
        generated_sql="SELECT name FROM buildings",
        sql_valid=True,
        validation_message="ok",
        rows=rows,
        rag_context=rag_context,
        errors=[],
    )

    primary_index = answer.index("Database results (primary answer):")
    guidance_index = answer.index("Supporting guidance from local documents:")
    assert primary_index < guidance_index, "rows must precede guidance in hybrid synthesis"
    assert "Citations: retrofit_guidelines.md." in answer
    assert "local retrofit documents" in answer


def test_synthesis_doc_only_with_no_rows_states_doc_limitation() -> None:
    answer = synthesize_agent_answer(
        question="What guidance applies to retrofits?",
        intent="document_policy_query",
        generated_sql="",
        sql_valid=True,
        validation_message="",
        rows=[],
        rag_context=[],
        errors=[],
    )
    assert "Local documents do not contain enough information" in answer


def test_synthesis_unsupported_returns_scope_message() -> None:
    answer = synthesize_agent_answer(
        question="Send an email",
        intent="unsupported",
        generated_sql="",
        sql_valid=False,
        validation_message="",
        rows=[],
        rag_context=[],
        errors=[],
    )
    assert "outside the current TwinQuery scope" in answer
