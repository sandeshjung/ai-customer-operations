import os
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from evaluation.retrieval.evaluate_retrieval import evaluate
from evaluation.agents.evaluate_delayed_order import evaluate_delayed_order_agent
from evaluation.agents.evaluate_triage import evaluate_triage_agent
from evaluation.utils import write_report


def main():
    print("=" * 70)
    print("RAG RETRIEVAL EVALUATION (free — no LLM calls)")
    print("=" * 70)
    retrieval_metrics = evaluate()

    faithfulness_metrics = {}
    if os.getenv("RUN_FAITHFULNESS"):
        from evaluation.retrieval.evaluate_faithfulness import evaluate_faithfulness

        print("\n" + "=" * 70)
        print("RAG FAITHFULNESS EVALUATION (opt-in — uses the LLM)")
        print("=" * 70)
        faithfulness_metrics = evaluate_faithfulness()
    else:
        print(
            "\nSkipping faithfulness eval (costs extra LLM calls). "
            "Set RUN_FAITHFULNESS=1 to include it."
        )

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

    # Gate: fail if any critical metric is below threshold.
    # Thresholds are intentionally loose given the small (15-scenario)
    # dataset sizes chosen to stay within a free-tier LLM budget — treat
    # these as smoke-test gates, not statistically rigorous benchmarks.
    gates = {
        "Recall@5": (retrieval_metrics.get("recall_at_5", 0), 0.60),
        "MRR": (retrieval_metrics.get("mrr", 0), 0.40),
        "Delay Severity Accuracy": (delay_metrics.get("severity_accuracy", 0), 0.70),
        "Delay Resolution Accuracy": (delay_metrics.get("resolution_accuracy", 0), 0.70),
        "Delay Escalation Accuracy": (delay_metrics.get("escalation_accuracy", 0), 0.70),
        "Triage Intent Accuracy": (triage_metrics.get("intent_accuracy", 0), 0.70),
        "Triage Sentiment Accuracy": (triage_metrics.get("sentiment_accuracy", 0), 0.60),
    }
    if faithfulness_metrics:
        gates["RAG Faithfulness"] = (faithfulness_metrics.get("faithfulness", 0), 0.70)

    all_passed = True
    gate_results = {}
    for name, (actual, threshold) in gates.items():
        status = "PASS" if actual >= threshold else "FAIL"
        if status == "FAIL":
            all_passed = False
        gate_results[name] = {"actual": actual, "threshold": threshold, "status": status}
        print(f"  {name}: {actual:.2%} (threshold: {threshold:.0%}) [{status}]")

    print(f"\n{'ALL GATES PASSED' if all_passed else 'SOME GATES FAILED'}")

    report_path = write_report(
        "eval_run",
        {
            "retrieval": retrieval_metrics,
            "faithfulness": faithfulness_metrics,
            "delayed_order": delay_metrics,
            "triage": triage_metrics,
            "gates": gate_results,
            "all_passed": all_passed,
        },
    )
    print(f"\nReport written to {report_path}")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
