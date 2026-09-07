import json
from pathlib import Path

from langchain_core.messages import HumanMessage

from app.agents.graphs.triage_agent import triage_graph

DATASET_PATH = Path("backend/evaluation/datasets/triage_scenarios.json")


def evaluate_triage_agent():
    with open(DATASET_PATH, encoding="utf-8") as f:
        scenarios = json.load(f)

    correct_intent = 0
    correct_priority = 0
    correct_action = 0
    total = len(scenarios)

    for scenario in scenarios:
        # Pass ticket as a message so the LLM sees the context
        ticket_message = HumanMessage(
            content=(
                f"Subject: {scenario['subject']}\n"
                f"Message: {scenario['message']}\n"
                f"Please triage this support ticket."
            )
        )

        result = triage_graph.invoke({
            "ticket_id": scenario["ticket_id"],
            "ticket": {
                "subject": scenario["subject"],
                "message": scenario["message"],
                "priority": "MEDIUM",
            },
            "customer_history": [],
            "policy_context": "",
            "messages": [ticket_message],  # some graphs may use messages
        })

        decision = result["decision"]

        intent_match = decision.intent.value == scenario["expected_intent"]
        priority_match = decision.priority == scenario["expected_priority"]
        action_match = decision.action.value == scenario["expected_action"]

        if intent_match:
            correct_intent += 1
        if priority_match:
            correct_priority += 1
        if action_match:
            correct_action += 1

        print(f"Ticket: {scenario['subject']}")
        print(f"  Expected: {scenario['expected_intent']} / {scenario['expected_priority']} / {scenario['expected_action']}")
        print(f"  Got:      {decision.intent.value} / {decision.priority} / {decision.action.value}")
        print(f"  Match:    intent={intent_match}, priority={priority_match}, action={action_match}")
        print("-" * 60)

    print(f"\nIntent Accuracy:   {correct_intent}/{total} = {correct_intent / total:.1%}")
    print(f"Priority Accuracy: {correct_priority}/{total} = {correct_priority / total:.1%}")
    print(f"Action Accuracy:   {correct_action}/{total} = {correct_action / total:.1%}")

    return {
        "intent_accuracy": correct_intent / total,
        "priority_accuracy": correct_priority / total,
        "action_action_accuracy": correct_action / total,
    }


if __name__ == "__main__":
    evaluate_triage_agent()