from app.rag.retriever import search_policy

def test_search_policy_returns():

    results = search_policy("What happens when an order is delayed more than 5 days?")

    assert len(results) > 0
    assert any (
        "shipping_policy" in result["source"]
        for result in results
    )