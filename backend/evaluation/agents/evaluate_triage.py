import json
from pathlib import Path

from langchain_core.messages import HumanMessage

from app.agents.graphs.triage_agent import triage_graph
from evaluation.utils import (
    Checkpoint,
    apply_eval_limit,
    paced_sleep,
    retry_with_backoff,
)

DATASET_PATH = Path("backend/evaluation/datasets/triage_scenarios.json")


def _run_scenario(scenario: dict) -> dict:
    ticket_message = HumanMessage(
        content=(
            f"Subject: {scenario['subject']}\n"
            f"Message: {scenario['message']}\n"
            f"Please triage this support ticket."
        )
    )

    result = retry_with_backoff(
        lambda: triage_graph.invoke(
            {
                "ticket_id": scenario["ticket_id"],
                "ticket": {
                    "subject": scenario["subject"],
                    "message": scenario["message"],
                    "priority": "MEDIUM",
                },
                "customer_history": [],
                "policy_context": "",
                "messages": [ticket_message],
            }
        ),
        description=f"triage scenario {scenario['ticket_id']}",
    )
    decision = result["decision"]

    return {
        "intent": decision.intent.value,
        "priority": decision.priority,
        "sentiment": decision.sentiment.value,
        "action": decision.action.value,
        "requires_human": decision.requires_human,
    }


def evaluate_triage_agent():
    with open(DATASET_PATH, encoding="utf-8") as f:
        scenarios = apply_eval_limit(json.load(f))

    checkpoint = Checkpoint("triage")

    correct_intent = 0
    correct_priority = 0
    correct_sentiment = 0
    correct_action = 0
    completed = 0
    failed = []

    for scenario in scenarios:
        cached = checkpoint.get(scenario["ticket_id"])
        if cached:
            got = cached["got"]
            print(f"Ticket: {scenario['subject']} (cached)")
        else:
            try:
                got = _run_scenario(scenario)
            except Exception as exc:
                print(f"FAIL | {scenario['subject']}: {exc}")
                failed.append({"ticket_id": scenario["ticket_id"], "error": str(exc)})
                paced_sleep()
                continue
            checkpoint.record(
                scenario["ticket_id"],
                {
                    "subject": scenario["subject"],
                    "expected": {
                        "intent": scenario["expected_intent"],
                        "priority": scenario["expected_priority"],
                        "sentiment": scenario["expected_sentiment"],
                        "action": scenario["expected_action"],
                    },
                    "got": got,
                },
            )
            paced_sleep()
            print(f"Ticket: {scenario['subject']}")

        intent_match = got["intent"] == scenario["expected_intent"]
        priority_match = got["priority"] == scenario["expected_priority"]
        sentiment_match = got["sentiment"] == scenario["expected_sentiment"]
        action_match = got["action"] == scenario["expected_action"]

        if intent_match:
            correct_intent += 1
        if priority_match:
            correct_priority += 1
        if sentiment_match:
            correct_sentiment += 1
        if action_match:
            correct_action += 1
        completed += 1

        print(
            f"  Expected: {scenario['expected_intent']} / {scenario['expected_priority']} / "
            f"{scenario['expected_sentiment']} / {scenario['expected_action']}"
        )
        print(
            f"  Got:      {got['intent']} / {got['priority']} / "
            f"{got['sentiment']} / {got['action']}"
        )
        print(
            f"  Match:    intent={intent_match}, priority={priority_match}, "
            f"sentiment={sentiment_match}, action={action_match}"
        )
        print("-" * 60)

    total = completed or 1

    print(f"\nCompleted: {completed}/{len(scenarios)} (failed: {len(failed)})")
    print(f"Intent Accuracy:    {correct_intent}/{completed} = {correct_intent / total:.1%}")
    print(f"Priority Accuracy:  {correct_priority}/{completed} = {correct_priority / total:.1%}")
    print(f"Sentiment Accuracy: {correct_sentiment}/{completed} = {correct_sentiment / total:.1%}")
    print(f"Action Accuracy:    {correct_action}/{completed} = {correct_action / total:.1%}")

    return {
        "total_scenarios": len(scenarios),
        "completed": completed,
        "failed": failed,
        "intent_accuracy": correct_intent / total,
        "priority_accuracy": correct_priority / total,
        "sentiment_accuracy": correct_sentiment / total,
        "action_accuracy": correct_action / total,
    }


if __name__ == "__main__":
    evaluate_triage_agent()
