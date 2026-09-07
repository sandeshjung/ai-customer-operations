import json
from datetime import date
from pathlib import Path

from langchain_core.messages import HumanMessage

from app.agents.graphs.delayed_order import delayed_order_graph
from app.agents.state import DelayedOrderState
from app.core.logging import configure_logging
from evaluation.utils import (
    Checkpoint,
    apply_eval_limit,
    paced_sleep,
    retry_with_backoff,
)

configure_logging()

DATASET_PATH = Path("backend/evaluation/datasets/delayed_order_scenarios.json")
TODAY = date(2026, 9, 5)


def _run_scenario(scenario: dict) -> dict:
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

    result = retry_with_backoff(
        lambda: delayed_order_graph.invoke(state),
        description=f"delayed_order scenario {scenario['order_id']}",
    )
    decision = result["decision"]

    return {
        "severity": decision.severity.value,
        "resolution": decision.resolution.value,
        "requires_human": decision.requires_human,
    }


def evaluate_delayed_order_agent():
    with open(DATASET_PATH, encoding="utf-8") as f:
        scenarios = apply_eval_limit(json.load(f))

    checkpoint = Checkpoint("delayed_order")

    correct_severity = 0
    correct_resolution = 0
    correct_human = 0
    completed = 0
    failed = []

    for scenario in scenarios:
        cached = checkpoint.get(scenario["order_id"])
        if cached:
            got = cached["got"]
            print(f"Scenario: {scenario['description']} (cached)")
        else:
            try:
                got = _run_scenario(scenario)
            except Exception as exc:
                print(f"FAIL | {scenario['description']}: {exc}")
                failed.append({"order_id": scenario["order_id"], "error": str(exc)})
                paced_sleep()
                continue
            checkpoint.record(
                scenario["order_id"],
                {
                    "description": scenario["description"],
                    "expected": {
                        "severity": scenario["expected_severity"],
                        "resolution": scenario["expected_resolution"],
                        "requires_human": scenario["expected_requires_human"],
                    },
                    "got": got,
                },
            )
            paced_sleep()
            print(f"Scenario: {scenario['description']}")

        severity_match = got["severity"] == scenario["expected_severity"]
        resolution_match = got["resolution"] == scenario["expected_resolution"]
        human_match = got["requires_human"] == scenario["expected_requires_human"]

        if severity_match:
            correct_severity += 1
        if resolution_match:
            correct_resolution += 1
        if human_match:
            correct_human += 1
        completed += 1

        print(
            f"  Expected: {scenario['expected_severity']} / "
            f"{scenario['expected_resolution']} / human={scenario['expected_requires_human']}"
        )
        print(
            f"  Got:      {got['severity']} / {got['resolution']} / "
            f"human={got['requires_human']}"
        )
        print(
            f"  Match:    severity={severity_match}, resolution={resolution_match}, "
            f"human={human_match}"
        )
        print("-" * 60)

    total = completed or 1

    print(f"\nCompleted: {completed}/{len(scenarios)} (failed: {len(failed)})")
    print(f"Severity Accuracy:     {correct_severity}/{completed} = {correct_severity / total:.1%}")
    print(f"Resolution Accuracy:   {correct_resolution}/{completed} = {correct_resolution / total:.1%}")
    print(f"Escalation Accuracy:   {correct_human}/{completed} = {correct_human / total:.1%}")

    return {
        "total_scenarios": len(scenarios),
        "completed": completed,
        "failed": failed,
        "severity_accuracy": correct_severity / total,
        "resolution_accuracy": correct_resolution / total,
        "human_flag_accuracy": correct_human / total,
        "escalation_accuracy": correct_human / total,
    }


if __name__ == "__main__":
    evaluate_delayed_order_agent()
