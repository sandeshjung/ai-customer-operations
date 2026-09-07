import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from evaluation.retrieval.evaluate_retrieval import evaluate
from evaluation.agents.evaluate_delayed_order import evaluate_delayed_order_agent
from evaluation.agents.evaluate_triage import evaluate_triage_agent


def main():
    print("=" * 70)
    print("RAG RETRIEVAL EVALUATION")
    print("=" * 70)
    retrieval_metrics = evaluate()

    print("\n" + "=" * 70)
    print("DELAYED ORDER AGENT EVALUATION")
    print("=" * 70)
    delay_metrics = evaluate_delayed_order_agent()

    print("\n" + "=" * 70)
    print("TRIAGE AGENT EVALUATION")
    print("=" * 70)
    triage_metrics = evaluate_triage_agent()

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    # Gate: fail if any critical metric is below threshold
    gates = {
        "Recall@5": (retrieval_metrics.get("recall_at_5", 0), 0.60),
        "MRR": (retrieval_metrics.get("mrr", 0), 0.40),
        "Delay Severity Accuracy": (delay_metrics.get("severity_accuracy", 0), 0.70),
        "Delay Resolution Accuracy": (delay_metrics.get("resolution_accuracy", 0), 0.70),
        "Triage Intent Accuracy": (triage_metrics.get("intent_accuracy", 0), 0.70),
    }

    all_passed = True
    for name, (actual, threshold) in gates.items():
        status = "PASS" if actual >= threshold else "FAIL"
        if status == "FAIL":
            all_passed = False
        print(f"  {name}: {actual:.2%} (threshold: {threshold:.0%}) [{status}]")

    print(f"\n{'ALL GATES PASSED' if all_passed else 'SOME GATES FAILED'}")
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())