from crossref_verifier import _title_similarity, _record_summary


def test_title_similarity_exact():
    assert _title_similarity("A Study of RAG", "A Study of RAG") == 1.0


def test_record_summary_maps_crossref_fields():
    record = {
        "title": ["Paper title"],
        "DOI": "10.1234/example",
        "author": [{"given": "Jane", "family": "Doe"}],
        "container-title": ["Example Journal"],
        "published-print": {"date-parts": [[2024, 2, 1]]},
        "page": "10-20",
    }
    summary = _record_summary(record)
    assert summary["article_title"] == "Paper title"
    assert summary["authors"] == ["Jane Doe"]
    assert summary["publication_year"] == "2024"
    assert summary["page_range"] == "10-20"
