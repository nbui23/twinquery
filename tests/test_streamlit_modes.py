from app.streamlit_app import MODES

def test_streamlit_modes_include_hybrid() -> None:
    assert MODES[0] == "Hybrid Digital Twin Query"
    assert "Map query" in MODES
    assert "Document RAG" in MODES
