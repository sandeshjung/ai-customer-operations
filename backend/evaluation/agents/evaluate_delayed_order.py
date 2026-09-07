import json
from datetime import date
from pathlib import Path

from langchain_core.messages import HumanMessage

from app.agents.graphs.delayed_order import delayed_order_graph
from app.agents.state import DelayedOrderState
from app.core.logging import configure_logging

configure_logging()

DATASET_PATH = Path("backend/evaluation/datasets/delayed_order_scenarios.json")
TODAY = date(2026, 9, 5)


def evaluate_delayed_order_agent():
    with open(DATASET_PATH, encoding="utf-8") as f:
        scenarios = json.load(f)

    correct_severity = 0
    correct_resolution = 0
    correct_human = 0
    total = len(scenarios)

    for scenario in scenarios:
        delay_days = (TODAY - date.fromisoformat(scenario["expected_delivery"])).days

        # Build a realistic message history so the LLM sees the order context
        initial_message = HumanMessage(
            content=(
                f"Investigate delayed order {scenario['order_id']}. "
                f"Order is {delay_days} days late. "
                f"Expected delivery was {scenario['expected_delivery']}. "
                f"Shipment status: {scenario['shipment_status'] or 'no shipment record'}."
            )
        )

        state = DelayedOrderState(
            messages=[initial_message],
            order_id=scenario["order_id"],
            order=None,
            shipment=None,
            customer=None,
            delay_days=delay_days,
            decision=None,
            requires_human=False,
            tool_iterations=0,
            evidence=[],
        )

        try:
            result = delayed_order_graph.invoke(state)
            decision = result["decision"]
        except Exception as exc:
            print(f"FAIL | {scenario['description']}: {exc}")
            continue

        severity_match = decision.severity.value == scenario["expected_severity"]
        resolution_match = decision.resolution.value == scenario["expected_resolution"]
        human_match = decision.requires_human == scenario["expected_requires_human"]

        if severity_match:
            correct_severity += 1
        if resolution_match:
            correct_resolution += 1
        if human_match:
            correct_human += 1

        print(f"Scenario: {scenario['description']}")
        print(f"  Expected: {scenario['expected_severity']} / {scenario['expected_resolution']} / human={scenario['expected_requires_human']}")
        print(f"  Got:      {decision.severity.value} / {decision.resolution.value} / human={decision.requires_human}")
        print(f"  Match:    severity={severity_match}, resolution={resolution_match}, human={human_match}")
        print("-" * 60)

    print(f"\nSeverity Accuracy:     {correct_severity}/{total} = {correct_severity / total:.1%}")
    print(f"Resolution Accuracy:   {correct_resolution}/{total} = {correct_resolution / total:.1%}")
    print(f"Human Flag Accuracy:   {correct_human}/{total} = {correct_human / total:.1%}")

    return {
        "severity_accuracy": correct_severity / total,
        "resolution_accuracy": correct_resolution / total,
        "human_flag_accuracy": correct_human / total,
    }


if __name__ == "__main__":
    evaluate_delayed_order_agent()