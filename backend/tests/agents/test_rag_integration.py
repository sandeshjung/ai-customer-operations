from app.agents.graphs.delayed_order import (
    search_shipping_policy,
)


def test_policy_tool_returns_shipping_policy():

    result = search_shipping_policy.invoke(
        {
            "query": (
                "What should happen when an order "
                "is delayed more than five days?"
            )
        }
    )

    assert result

    assert any(
        "shipping_policy" in item["source"]
        for item in result
    )