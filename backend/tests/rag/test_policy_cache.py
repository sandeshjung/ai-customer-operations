import pytest
from app.rag import service

PREFIX = "what happens when an order is delayed and the shipment "


@pytest.fixture
def searches(monkeypatch):
    """Records the queries that reached hybrid_search (i.e. cache misses)."""
    seen = []

    def fake_hybrid_search(query, limit=5):
        seen.append(query)
        return [{"content": f"result for {query}", "source": "shipping_policy.pdf"}]

    monkeypatch.setattr(service, "hybrid_search", fake_hybrid_search)
    service.retrieve_policy_cached.cache_clear()
    yield seen
    service.retrieve_policy_cached.cache_clear()


def test_long_queries_sharing_a_prefix_do_not_collide(searches):
    """Regression test: the cache key was the query truncated to 50
    characters, so these two returned the same cached result."""
    lost = service.retrieve_policy(PREFIX + "is marked lost by the carrier?")
    damaged = service.retrieve_policy(PREFIX + "arrives damaged?")

    assert lost != damaged
    assert len(searches) == 2


def test_search_runs_on_the_full_query(searches):
    """Regression test: the truncated key was also what got searched, so a
    long query was matched on its first 50 characters only."""
    query = PREFIX + "is marked lost by the carrier?"

    service.retrieve_policy(query)

    assert searches == [query]


def test_case_and_whitespace_variants_share_a_cache_entry(searches):
    service.retrieve_policy("Refund  policy for late orders")
    service.retrieve_policy("refund policy for LATE orders ")

    assert searches == ["refund policy for late orders"]


def test_mutating_a_result_does_not_change_the_cache(searches):
    first = service.retrieve_policy("refund policy")
    first[0]["content"] = "tampered"
    first.append({"content": "extra"})

    second = service.retrieve_policy("refund policy")

    assert second == [
        {"content": "result for refund policy", "source": "shipping_policy.pdf"}
    ]
