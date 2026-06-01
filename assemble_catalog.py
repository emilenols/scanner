"""
Assemble final catalog + finalize the manifest.
Merges batch results with Phase A inventory, applies confidence routing,
records the processing block, hashes outputs, finalizes, and uploads
catalog + manifest to the client's GCS bucket.
"""
import os
import json

import pandas as pd
from google.cloud import storage

from config import load_config, routing
from manifest import Manifest

INV = os.path.expanduser("~/scanner/phase_a_inventory.jsonl")
RESULTS = os.path.expanduser("~/scanner/batch_results.jsonl")


def main():
    cfg = load_config()
    m = Manifest.resume_or_start(cfg)
    r = routing(cfg)
    accept, review_t, fb_model = (r["accept_threshold"], r["review_threshold"],
                                  r["fallback_model"])

    phase_a = {}
    with open(INV) as f:
        for line in f:
            rec = json.loads(line)
            phase_a[rec["drive_id"]] = rec

    rows = []
    with open(RESULTS) as f:
        for line in f:
            e = json.loads(line)
            did = e.get("key")
            resp = e.get("response", {})
            if not did or "candidates" not in resp:
                continue
            try:
                text = resp["candidates"][0]["content"]["parts"][0]["text"]
                cls = json.loads(text)
            except Exception:
                continue
            conf = cls.get("confidence", 0)
            rows.append({**phase_a.get(did, {}), **cls,
                         "review_required": conf < accept,
                         "fallback_candidate": conf < review_t,
                         "schema_version": "v2.1"})

    df = pd.DataFrame(rows)
    base = os.path.expanduser("~/scanner/catalog_v1")
    df.to_json(f"{base}.jsonl", orient="records", lines=True)
    df.to_csv(f"{base}.csv", index=False)
    df.to_parquet(f"{base}.parquet")
    print(f"Wrote {len(df)} rows to catalog_v1.{{jsonl,csv,parquet}}")

    review = int(df["review_required"].sum()) if len(df) else 0
    fb = int(df["fallback_candidate"].sum()) if len(df) else 0
    rate = round(100 * df["review_required"].mean(), 1) if len(df) else 0.0

    m.add_processing(pass_name="pass1", model=r["model"],
                     confidence_threshold_accept=accept,
                     confidence_threshold_review=review_t,
                     confidence_threshold_fallback=review_t,
                     fallback_model=fb_model,
                     counts_accepted=len(df) - review,
                     counts_review_queue=review,
                     counts_fallback_invoked=fb, review_rate_pct=rate)

    # Upload catalog
    bucket = cfg["gcp"]["bucket"]
    gcs = storage.Client()
    for ext in ("jsonl", "csv", "parquet"):
        gcs.bucket(bucket).blob(f"pass1/catalog_v1.{ext}") \
            .upload_from_filename(f"{base}.{ext}")
        print(f"Uploaded gs://{bucket}/pass1/catalog_v1.{ext}")

    # Finalize + upload manifest (will raise if Gate B / data_scope missing).
    # Client approver is intentionally NOT set here — it is filled by a real
    # client action (client_signoff.py), not echoed from config.
    m.finalize(
        catalog_files={f"catalog_v1.{ext}": f"{base}.{ext}"
                       for ext in ("jsonl", "csv", "parquet")},
        operator_name=cfg.get("operator", "Focusfinder Consulting"),
        total_rows=len(df), review_rate_pct=rate)
    uri = m.upload_gcs(bucket)
    print(f"Finalized manifest -> {uri}")
    print("Operator attestation recorded. Client sign-off still PENDING:")
    print("  after Lloyd reviews the catalog, run:")
    print('  python client_signoff.py --approver "<name>" --role "<role>" --confirm')

    print("\n=== Final Catalog ===")
    print(f"Total: {len(df)} | Review: {review} ({rate}%) | Fallback candidates: {fb}")
    if len(df):
        print("\nBy type:\n" + df["document_type"].value_counts().to_string())


if __name__ == "__main__":
    main()
