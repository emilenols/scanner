"""
Pilot — sampled eligible files, classified CONCURRENTLY for fast feedback.
Config-driven taxonomy + thresholds. Produces pilot_catalog.{jsonl,csv} and the
Gate B review instructions. Does NOT auto-pass Gate B — a human must run gate_b.py.
"""
import os
import json
import socket
import random
import threading
import concurrent.futures
from datetime import datetime, timezone
from collections import Counter

from google.oauth2 import service_account
from googleapiclient.discovery import build
from google import genai
from google.genai import types
from tqdm import tqdm
from tenacity import retry, stop_after_attempt, wait_exponential

from config import (load_config, build_pass1_model, system_instruction,
                    routing, verify_model)
from manifest import Manifest
import reader

PILOT_SIZE = 200
SEED = 42
MAX_WORKERS = 8          # concurrent classifications
SYNC_TIMEOUT = 90        # seconds per file, so one slow file can't hang the run
PROMPT = "Classify this document according to the instructions."
INV = os.path.expanduser("~/scanner/phase_a_inventory.jsonl")
OUT = os.path.expanduser("~/scanner/pilot_catalog.jsonl")

socket.setdefaulttimeout(SYNC_TIMEOUT)

cfg = load_config()
ACCEPT = routing(cfg)["accept_threshold"]
MODEL = routing(cfg)["model"]
Pass1 = build_pass1_model(cfg)
SYS = system_instruction(cfg)
INCLUDE_IMAGES = cfg.get("scan", {}).get("include_images", True)
KEY_PATH = os.environ["GOOGLE_APPLICATION_CREDENTIALS"]
API_KEY = os.environ["GEMINI_API_KEY"]

# Per-thread clients (googleapiclient/httplib2 is NOT thread-safe)
_local = threading.local()


def _clients():
    if not hasattr(_local, "drive"):
        creds = service_account.Credentials.from_service_account_file(
            KEY_PATH, scopes=["https://www.googleapis.com/auth/drive.readonly"])
        _local.drive = build("drive", "v3", credentials=creds)
        _local.gem = genai.Client(api_key=API_KEY)
    return _local.drive, _local.gem


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=20))
def _classify(gem, result):
    resp = gem.models.generate_content(
        model=MODEL, contents=reader.sync_contents(result, PROMPT),
        config=types.GenerateContentConfig(
            system_instruction=SYS, response_mime_type="application/json",
            response_schema=Pass1, temperature=0.1))
    return json.loads(resp.text)


def worker(r):
    drive, gem = _clients()
    try:
        result = reader.read_for_model(drive, r, INCLUDE_IMAGES)
    except reader.UnreadableDocument as e:
        return "fail", {"drive_id": r["drive_id"], "filename": r["filename"],
                        "error": f"unreadable: {e.reason}"}
    try:
        cls = _classify(gem, result)
        return "ok", {**r, **cls,
                      "review_required": cls["confidence"] < ACCEPT,
                      "scan_timestamp": datetime.now(timezone.utc).isoformat(),
                      "schema_version": "v2.1"}
    except Exception as e:
        return "fail", {"drive_id": r["drive_id"], "filename": r["filename"],
                        "error": str(e)[:200]}


def main():
    m = Manifest.resume_or_start(cfg)
    _, gem = _clients()
    verify_model(gem, MODEL)  # fail fast on a stale/wrong model string
    with open(INV) as f:
        inv = [json.loads(l) for l in f]
    cand = [r for r in inv if reader.is_eligible(r, INCLUDE_IMAGES)]
    print(f"{len(cand)} eligible files")
    random.seed(SEED)
    sample = random.sample(cand, min(PILOT_SIZE, len(cand)))
    print(f"Sampling {len(sample)} for pilot ({MAX_WORKERS}-way concurrent)")
    m.log_command("agent", "pilot classify (concurrent)", f"{len(sample)} docs", "success")

    results, failures = [], []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = [ex.submit(worker, r) for r in sample]
        for fut in tqdm(concurrent.futures.as_completed(futures),
                        total=len(sample), desc="Pilot classify"):
            status, payload = fut.result()
            (results if status == "ok" else failures).append(payload)

    with open(OUT, "w") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")
    print(f"\nWrote {len(results)} pilot results to {OUT}")
    if failures:
        with open(os.path.expanduser("~/scanner/pilot_failures.jsonl"), "w") as f:
            for r in failures:
                f.write(json.dumps(r) + "\n")
        print(f"{len(failures)} failures logged")

    review = sum(1 for r in results if r["review_required"])
    rate = 100 * review / max(len(results), 1)
    print("\n=== Pilot Summary ===")
    print(f"Classified: {len(results)} | Review (<{ACCEPT}): {review} ({rate:.1f}%)")
    for t, c in Counter(r["document_type"] for r in results).most_common():
        print(f"  {t}: {c}")

    try:
        import pandas as pd
        pd.read_json(OUT, lines=True).to_csv(
            os.path.expanduser("~/scanner/pilot_catalog.csv"), index=False)
        print("\nWrote pilot_catalog.csv for Gate B review.")
    except Exception:
        pass

    g = cfg["gates"]["gate_b_approver"]
    print("\n----- GATE B (human) -----")
    print("1. Download pilot_catalog.csv (Cloud Shell : -> Download)")
    print("2. Open 20 random rows; compare each file in Drive vs document_type/language")
    print("3. Record the verdict (this writes it into the manifest):")
    print(f'   python gate_b.py --sample 20 --correct <N> '
          f'--approver "{g["name"]}" --role "{g["role"]}"')
    print(f"   Gate passes if correct >= 18 AND review rate < 20% (now {rate:.1f}%)")


if __name__ == "__main__":
    main()
