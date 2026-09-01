from app.rag.retriever import search_policy


def test_shipping_policy_retrieval():

    results = search_policy(
        "What happens when an order is delayed more than 5 days?"
    )

    assert results

    assert any(
        "shipping_policy" in result["source"]
        for result in results
    )


def test_refund_policy_retrieval():

    results = search_policy(
        "Does a delayed shipment automatically qualify for a refund?"
    )

    assert results

    assert any(
        "refund_policy" in result["source"]
        for result in results
    )


def test_return_policy_retrieval():

    results = search_policy(
        "How long does a customer have to return an item?"
    )

    assert results

    assert any(
        "return_policy" in result["source"]
        for result in results
    )


def test_warranty_policy_retrieval():

    results = search_policy(
        "What happens when a product is defective?"
    )

    assert results

    assert any(
        "warranty_policy" in result["source"]
        for result in results
    )