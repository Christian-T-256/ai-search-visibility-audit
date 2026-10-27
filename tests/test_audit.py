from pathlib import Path

from ai_search_visibility_audit import DirectorySiteFetcher, audit_site, extract_schema_types
from ai_search_visibility_audit.audit import SIGNALS


FIXTURES = Path(__file__).resolve().parents[1] / "ai_search_visibility_audit" / "fixtures"
URL = "https://northwind-dental.example"


def test_signal_weights_total_100():
    assert sum(weight for _, weight, _ in SIGNALS) == 100
    assert len(SIGNALS) == 15


def test_fixture_audit_has_expected_score_and_priorities():
    fetcher = DirectorySiteFetcher(FIXTURES / "northwind-dental", URL)
    result = audit_site(URL, fetcher)

    assert result.score == 37
    assert result.grade == "F"
    assert result.earned_points == 37
    assert result.fixes[0].key == "llms_txt"
    states = {signal.key: signal.passed for signal in result.signals}
    assert states["robots_txt"] is True
    assert states["direct_answer_para"] is True
    assert states["org_schema"] is False


def test_schema_type_extraction_handles_graphs_arrays_and_nested_entities():
    schema = {
        "@context": "https://schema.org",
        "@graph": [
            {"@type": ["Organization", "LocalBusiness"]},
            {"@type": "Article", "author": {"@type": "Person"}},
        ],
    }
    assert extract_schema_types(schema) == {"Organization", "LocalBusiness", "Article", "Person"}
