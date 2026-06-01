"""
Pilot — 200 sampled PDF/Word files, synchronous Gemini calls for fast feedback.
Config-driven taxonomy + thresholds. Produces pilot_catalog.{jsonl,csv} and the
Gate B review instructions. Does NOT auto-pass Gate B — a human must run gate_b.py.
"""
import os
import io
import json
import random
from datetime import datetime, timezone
from collections import Counter

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google import genai
from google.genai import types
from tqdm import tqdm
from tenacity import retry, stop_after_attempt, wait_exponential

from config import (load_config, build_pass1_model, system_instruction,
                    routing, verify_model)
from manifest import Manifest

PILOT_SIZE = 200
SEED = 42
INV = os.path.expanduser("~/scanner/phase_a_inventory.jsonl")
OUT = os.path.expanduser("~/scanner/pilot_catalog.jsonl")

cfg = load_config()
ACCEPT = routing(cfg)["accept_threshold"]
MODEL = routing(cfg)["model"]
Pass1 = build_pass1_model(cfg)
SYS = system_instruction(cfg)

creds = service_account.Credentials.from_service_account_file(
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"],
    scopes=["https://www.googleapis.com/auth/drive.readonly"])
drive = build("drive", "v3", credentials=creds)
gemini = genai.Client(api_key=os.environ["GEMINI_API_KEY"])


def download(file_id: str) -> bytes:
    req = drive.files().get_media(fileId=file_id)
    buf = io.BytesIO()
    dl = MediaIoBaseDownload(buf, req)
    done = False
    while not done:
        _, done = dl.next_chunk()
    return buf.getvalue()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=20))
def classify(content: bytes, mime: str) -> dict:
    resp = gemini.models.generate_content(
        model=MODEL,
        contents=[types.Part.from_bytes(data=content, mime_type=mime),
                  "Classify this document according to the instructions."],
        config=types.GenerateContentConfig(
            system_instruction=SYS, response_mime_type="application/json",
            response_schema=Pass1, temperature=0.1))
    return json.loads(resp.text)


def main():
    m = Manifest.resume_or_start(cfg)
    verify_model(gemini, MODEL)  # fail fast on a stale/wrong model string
    with open(INV) as f:
        inv = [json.loads(l) for l in f]
    cand = [r for r in inv if r["format_bucket"] in ("PDF", "Word")
            and r["skip_reason"] is None]
    print(f"{len(cand)} eligible PDF/Word files")
    random.seed(SEED)
    sample = random.sample(cand, min(PILOT_SIZE, len(cand)))
    print(f"Sampling {len(sample)} for pilot")
    m.log_command("agent", "pilot classify (sync)", f"{len(sample)} docs", "success")

    results, failures = [], []
    for r in tqdm(sample, desc="Pilot classify"):
        try:
            cls = classify(download(r["drive_id"]), r["mime_type"])
            results.append({**r, **cls,
                            "review_required": cls["confidence"] < ACCEPT,
                            "scan_timestamp": datetime.now(timezone.utc).isoformat(),
                            "schema_version": "v2.1"})
        except Exception as e:
            failures.append({"drive_id": r["drive_id"], "filename": r["filename"],
                             "error": str(e)})

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

    # CSV for human review
    try:
        import pandas as pd
        pd.read_json(OUT, lines=True).to_csv(
            os.path.expanduser("~/scanner/pilot_catalog.csv"), index=False)
        print("\nWrote pilot_catalog.csv for Gate B review.")
    except Exception:
        pass

    g = cfg["gates"]["gate_b_approver"]
    print("\n----- GATE B (human) -----")
    print("1. Download pilot_catalog.csv (Cloud Shell ⋮ -> Download)")
    print("2. Open 20 random rows; compare each file in Drive vs document_type/language")
    print("3. Record the verdict (this writes it into the manifest):")
    print(f'   python gate_b.py --sample 20 --correct <N> '
          f'--approver "{g["name"]}" --role "{g["role"]}"')
    print(f"   Gate passes if correct >= 18 AND review rate < 20% (now {rate:.1f}%)")


if __name__ == "__main__":
    main()
