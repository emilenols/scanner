"""
gate_b.py — record the human pilot review (Gate B) into the manifest.

This is the human oversight gate. It is intentionally a separate, explicit
command run by the named approver — the manifest then carries WHO approved,
WHEN, the sample, and the verdict.

Usage:
  python gate_b.py --sample 20 --correct 19 --approver "Alex X" --role "Implementation Lead"
"""
import argparse
import json
import os

from config import load_config
from manifest import Manifest

PILOT = os.path.expanduser("~/scanner/pilot_catalog.jsonl")


def review_rate() -> float:
    with open(PILOT) as f:
        rows = [json.loads(l) for l in f]
    if not rows:
        return 0.0
    review = sum(1 for r in rows if r.get("review_required"))
    return 100 * review / len(rows)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--sample", type=int, required=True)
    p.add_argument("--correct", type=int, required=True)
    p.add_argument("--approver", required=True)
    p.add_argument("--role", required=True)
    p.add_argument("--notes", default="")
    a = p.parse_args()

    cfg = load_config()
    m = Manifest.resume_or_start(cfg)
    rate = review_rate()

    passes = a.correct >= 18 and rate < 20.0
    status = "passed" if passes else "failed"
    m.record_gate("B_pilot_review", status, a.approver, a.role,
                  sample_size=a.sample, sample_correct=a.correct,
                  review_rate_pct=round(rate, 1), notes=a.notes)

    print(f"Gate B recorded: {status.upper()}")
    print(f"  Sample {a.correct}/{a.sample} correct | review rate {rate:.1f}%")
    if passes:
        print("  -> Proceed to full Pass 1: python pass1_scanner.py")
    else:
        print("  -> Gate B FAILED. Do not proceed. Escalate to Emile.")
        if a.correct < 18:
            print("     Reason: classification accuracy below 18/20.")
        if rate >= 20.0:
            print("     Reason: review rate >= 20% (likely scanned/legacy PDFs).")


if __name__ == "__main__":
    main()
