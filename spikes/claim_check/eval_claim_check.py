"""
Eval harness for claim_check.check_claim() against labeled_claims.json.

Usage:
    python eval_claim_check.py --fake                 # offline plumbing check
    python eval_claim_check.py --limit 5               # real Gemini, first 5
    python eval_claim_check.py                          # real Gemini, all

Without --fake and without GEMINI_API_KEY/GOOGLE_API_KEY set, this exits 2
immediately with no network call attempted (see main()).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from claim_check import check_claim, DEFAULT_MODEL  # noqa: E402

HERE = Path(__file__).parent
HARNESS_DIR = HERE.parent / "harness"
LABELED_PATH = HERE / "labeled_claims.json"
CONTRACT_PATH = HARNESS_DIR / "fake_contract.json"
OUT_DIR = HERE / "out"
_VERDICTS = ("contradiction", "consistent", "unclear")

# ponytail: sleep-ms default of 4500ms (~13 req/min) is a conservative guess —
# Gemini free-tier RPM per model isn't published as a fixed number we can cite
# here, so this stays well under any plausible free-tier ceiling rather than
# discovering the limit via 429s. Tune down once a real RPM is observed.
DEFAULT_SLEEP_MS = 4500


class FakeClient:
    """Deterministic stub matching the google-genai client shape, keyword-based.
    ponytail: for offline plumbing only, not tuned for label accuracy."""

    class _Models:
        def generate_content(self, model, contents, config):
            import re

            m = re.search(r'Rep sentence: "(.*)"', contents)
            text = (m.group(1) if m else contents).lower()
            verdict, clause_id, confidence = "unclear", None, 0.4

            if "seat" in text or "discount" in text:
                clause_id = "3.1"
                verdict = (
                    "contradiction"
                    if ("discount" in text or "fifty-one" in text)
                    else "consistent"
                )
                confidence = 0.85
            elif any(k in text for k in ("notice", "cancel", "renew", "terminat")):
                clause_id = "4.2"
                verdict = (
                    "contradiction"
                    if any(k in text for k in ("any time", "anytime", "thirty days", "strings"))
                    else "consistent"
                )
                confidence = 0.85
            elif any(k in text for k in ("data", "delete", "backup", "archive", "recoverable")):
                clause_id = "5.3"
                verdict = (
                    "contradiction"
                    if any(k in text for k in ("forever", "sixty days", "no backup"))
                    else "consistent"
                )
                confidence = 0.8
            elif any(k in text for k in ("p1", "support", "hour", "24", "round-the-clock", "twenty four")):
                clause_id = "6.1"
                verdict = (
                    "contradiction"
                    if any(k in text for k in ("any day", "round-the-clock", "eight business", "twenty four seven"))
                    else "consistent"
                )
                confidence = 0.8

            class _Resp:
                text = json.dumps({"verdict": verdict, "clause_id": clause_id, "confidence": confidence})

            return _Resp()

    def __init__(self):
        self.models = self._Models()


def percentile(data: list[float], p: float) -> float:
    """Linear-interpolation percentile (matches numpy default). p in [0,100]."""
    if not data:
        return 0.0
    s = sorted(data)
    k = (len(s) - 1) * (p / 100.0)
    f, c = math.floor(k), math.ceil(k)
    if f == c:
        return s[int(k)]
    return s[f] + (s[c] - s[f]) * (k - f)


def compute_metrics(records: list[dict]) -> dict:
    """records: [{expected_verdict, expected_clause_id, predicted: <check_claim result>}]"""
    confusion = {(e, p): 0 for e in _VERDICTS for p in _VERDICTS}
    tp = fn = fp_alarm = neg_total = clause_correct = errors = 0
    latencies = []

    for r in records:
        exp, pred = r["expected_verdict"], r["predicted"]
        pv = pred["verdict"]
        confusion[(exp, pv)] = confusion.get((exp, pv), 0) + 1
        latencies.append(pred["latency_ms"])
        if pred.get("error"):
            errors += 1

        if exp == "contradiction":
            if pv == "contradiction":
                tp += 1
                if pred.get("clause_id") == r["expected_clause_id"]:
                    clause_correct += 1
            else:
                fn += 1
        else:
            neg_total += 1
            if pv == "contradiction":
                fp_alarm += 1

    contradiction_recall = (tp / (tp + fn)) if (tp + fn) else None
    false_alarm_rate = (fp_alarm / neg_total) if neg_total else None
    clause_id_accuracy = (clause_correct / tp) if tp else None

    return {
        "total": len(records),
        "confusion_matrix": {f"expected={e}|predicted={p}": c for (e, p), c in confusion.items()},
        "contradiction_recall": contradiction_recall,
        "false_alarm_rate": false_alarm_rate,
        "clause_id_accuracy_on_true_positives": clause_id_accuracy,
        "latency_ms_p50": percentile(latencies, 50),
        "latency_ms_p95": percentile(latencies, 95),
        "error_count": errors,
    }


def print_table(metrics: dict) -> None:
    print(f"\n{'metric':40s} value")
    print("-" * 55)
    for key in (
        "total",
        "contradiction_recall",
        "false_alarm_rate",
        "clause_id_accuracy_on_true_positives",
        "latency_ms_p50",
        "latency_ms_p95",
        "error_count",
    ):
        print(f"{key:40s} {metrics[key]}")
    print("\nconfusion matrix:")
    for k, v in metrics["confusion_matrix"].items():
        if v:
            print(f"  {k}: {v}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fake", action="store_true", help="use deterministic offline fake client, no network")
    parser.add_argument("--limit", type=int, default=None, help="only run first N labeled claims")
    parser.add_argument("--sleep-ms", type=int, default=DEFAULT_SLEEP_MS, help="sleep between real calls (ms)")
    parser.add_argument("--model", default=None, help="override model id")
    args = parser.parse_args(argv)

    if not args.fake:
        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not key:
            print(
                "No GEMINI_API_KEY or GOOGLE_API_KEY set, and --fake not given.\n"
                "Get a free key at https://aistudio.google.com/apikey and set it as an "
                "env var, or run with --fake for an offline plumbing check.",
                file=sys.stderr,
            )
            return 2

    labeled = json.loads(LABELED_PATH.read_text(encoding="utf-8"))
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    clauses = contract["clauses"]
    if args.limit:
        labeled = labeled[: args.limit]

    client = FakeClient() if args.fake else None
    records = []
    for i, item in enumerate(labeled):
        predicted = check_claim(item["sentence"], clauses, client=client, model=args.model)
        records.append({**item, "predicted": predicted})
        if not args.fake and i < len(labeled) - 1:
            time.sleep(args.sleep_ms / 1000.0)

    metrics = compute_metrics(records)
    print_table(metrics)

    OUT_DIR.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = OUT_DIR / f"eval_{ts}.json"
    report = {
        "timestamp_utc": ts,
        "fake": args.fake,
        "model": args.model or DEFAULT_MODEL,
        "metrics": metrics,
        "records": records,
    }
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nwrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
