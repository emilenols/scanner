"""
Full Pass 1 — Batch API submission (scalable architecture).

Instead of inlining document bytes into one giant JSONL (which doesn't scale and
times out on upload), each document is uploaded ONCE to the Gemini File API,
concurrently, and referenced by URI. The batch request file stays tiny.
File API uploads auto-delete after 48h (transient by design).

Word/Excel are sent as extracted text (small) inline; PDF/images are uploaded
and referenced. Refuses to run unless Gate B is recorded as passed.
"""
import os
import io
import json
import threading
import concurrent.futures
from datetime import datetime

from google.oauth2 import service_account
from googleapiclient.discovery import build
from google import genai
from tqdm import tqdm

from config import (load_config, build_pass1_model, system_instruction,
                    routing, verify_model)
from manifest import Manifest
import reader

INV = os.path.expanduser("~/scanner/phase_a_inventory.jsonl")
BATCH_REQ = os.path.expanduser("~/scanner/batch_requests.jsonl")
JOB_FILE = os.path.expanduser("~/scanner/batch_job.txt")
PROMPT = "Classify this document according to the instructions."
MAX_WORKERS = 8          # concurrent File API uploads

cfg = load_config()
MODEL = routing(cfg)["model"]
Pass1 = build_pass1_model(cfg)
SYS = system_instruction(cfg)
BUCKET = cfg["gcp"]["bucket"]
INCLUDE_IMAGES = cfg.get("scan", {}).get("include_images", True)
KEY_PATH = os.environ["GOOGLE_APPLICATION_CREDENTIALS"]
API_KEY = os.environ["GEMINI_API_KEY"]

# Per-thread Drive + Gemini clients (googleapiclient/httplib2 is NOT thread-safe)
_local = threading.local()


def _clients():
    if not hasattr(_local, "drive"):
        creds = service_account.Credentials.from_service_account_file(
            KEY_PATH, scopes=["https://www.googleapis.com/auth/drive.readonly"])
        _local.drive = build("drive", "v3", credentials=creds)
        _local.gem = genai.Client(api_key=API_KEY)
    return _local.drive, _local.gem


def make_part(record):
    """Read a document and return a request part (uploading media to the File
    API and referencing it; inlining extracted text). Returns None to skip."""
    drive, gem = _clients()
    try:
        result = reader.read_for_model(drive, record, INCLUDE_IMAGES, enforce_size_cap=False)
    except reader.UnreadableDocument:
        return None
    if result["kind"] == "media":
        up = gem.files.upload(file=io.BytesIO(result["bytes"]),
                              config={"mime_type": result["mime"]})
        return {"file_data": {"file_uri": up.uri, "mime_type": result["mime"]}}
    return {"text": f"Document content:\n\n{result['text']}"}


def build_requests(records, path):
    schema = Pass1.model_json_schema()
    skipped = 0
    lines = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(make_part, r): r for r in records}
        for fut in tqdm(concurrent.futures.as_completed(futures),
                        total=len(records), desc="Uploading + preparing"):
            r = futures[fut]
            try:
                part = fut.result()
            except Exception as e:
                print(f"  skip {r['filename']}: {str(e)[:80]}")
                skipped += 1
                continue
            if part is None:
                skipped += 1
                continue
            lines.append(json.dumps({
                "key": r["drive_id"],
                "request": {
                    "contents": [{"parts": [part, {"text": PROMPT}]}],
                    "system_instruction": {"parts": [{"text": SYS}]},
                    "generation_config": {
                        "response_mime_type": "application/json",
                        "response_schema": schema, "temperature": 0.1}}}))
    with open(path, "w") as out:
        out.write("\n".join(lines) + "\n")
    if skipped:
        print(f"  {skipped} files unreadable/failed, skipped")
    return len(lines)


def gate_b_passed(m: Manifest) -> bool:
    return any(g.gate == "B_pilot_review" and g.status.value == "passed"
               for g in m.m.human_gates)


def main():
    m = Manifest.resume_or_start(cfg)
    if not gate_b_passed(m):
        raise SystemExit("Gate B not passed in manifest. Run gate_b.py first.")
    gemini = genai.Client(api_key=API_KEY)
    verify_model(gemini, MODEL)

    with open(INV) as f:
        inv = [json.loads(l) for l in f]
    eligible = [r for r in inv if reader.is_eligible(r, INCLUDE_IMAGES)]
    print(f"Eligible: {len(eligible)}")
    if not eligible:
        print("Nothing to process.")
        return

    n = build_requests(eligible, BATCH_REQ)
    print(f"Built {n} batch requests ({os.path.getsize(BATCH_REQ)//1024} KB JSONL)")

    up = gemini.files.upload(file=BATCH_REQ, config={"mime_type": "application/jsonl"})
    m.log_command("agent", "upload batch input (File API)", up.name, "success")

    job = gemini.batches.create(
        model=MODEL, src=up.name,
        config={"display_name": f"{cfg['engagement_ref']}-pass1-"
                                f"{datetime.now().strftime('%Y%m%d-%H%M')}"})
    with open(JOB_FILE, "w") as f:
        f.write(job.name)
    m.log_command("agent", "gemini.batches.create", job.name, "success")
    print(f"\nSubmitted batch job: {job.name}")
    print("Saved to ~/scanner/batch_job.txt. You can close Cloud Shell; "
          "return in 1–24h and run: python check_batch.py")


if __name__ == "__main__":
    main()
