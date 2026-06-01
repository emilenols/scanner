"""
Full Pass 1 — Batch API submission. Server-side; Cloud Shell can be closed.
Refuses to run unless Gate B is recorded as passed. Idempotent via checkpoint.
"""
import os
import io
import json
import base64
from datetime import datetime

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google import genai
from google.cloud import storage
from tqdm import tqdm

from config import (load_config, build_pass1_model, system_instruction,
                    routing, verify_model)
from manifest import Manifest

INV = os.path.expanduser("~/scanner/phase_a_inventory.jsonl")
BATCH_REQ = os.path.expanduser("~/scanner/batch_requests.jsonl")
JOB_FILE = os.path.expanduser("~/scanner/batch_job.txt")

cfg = load_config()
MODEL = routing(cfg)["model"]
Pass1 = build_pass1_model(cfg)
SYS = system_instruction(cfg)
BUCKET = cfg["gcp"]["bucket"]

creds = service_account.Credentials.from_service_account_file(
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"],
    scopes=["https://www.googleapis.com/auth/drive.readonly"])
drive = build("drive", "v3", credentials=creds)
gemini = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
gcs = storage.Client()


def gate_b_passed(m: Manifest) -> bool:
    return any(g.gate == "B_pilot_review" and g.status.value == "passed"
               for g in m.m.human_gates)


def download(file_id: str) -> bytes:
    req = drive.files().get_media(fileId=file_id)
    buf = io.BytesIO()
    dl = MediaIoBaseDownload(buf, req)
    done = False
    while not done:
        _, done = dl.next_chunk()
    return buf.getvalue()


def build_requests(records, path):
    schema = Pass1.model_json_schema()
    with open(path, "w") as out:
        for r in tqdm(records, desc="Preparing batch"):
            try:
                b64 = base64.b64encode(download(r["drive_id"])).decode()
                out.write(json.dumps({
                    "key": r["drive_id"],
                    "request": {
                        "contents": [{"parts": [
                            {"inline_data": {"mime_type": r["mime_type"], "data": b64}},
                            {"text": "Classify this document according to the instructions."}]}],
                        "system_instruction": {"parts": [{"text": SYS}]},
                        "generation_config": {
                            "response_mime_type": "application/json",
                            "response_schema": schema, "temperature": 0.1}}}) + "\n")
            except Exception as e:
                print(f"Skipped {r['filename']}: {e}")


def main():
    m = Manifest.resume_or_start(cfg)
    if not gate_b_passed(m):
        raise SystemExit("Gate B not passed in manifest. Run gate_b.py first.")
    verify_model(gemini, MODEL)  # fail fast on a stale/wrong model string

    with open(INV) as f:
        inv = [json.loads(l) for l in f]
    eligible = [r for r in inv if r["format_bucket"] in ("PDF", "Word", "Excel", "Email")
                and r["skip_reason"] is None]
    print(f"Eligible: {len(eligible)}")
    if not eligible:
        print("Nothing to process.")
        return

    build_requests(eligible, BATCH_REQ)
    gcs_in = "pass1/batch_input.jsonl"
    gcs.bucket(BUCKET).blob(gcs_in).upload_from_filename(BATCH_REQ)
    m.log_command("agent", "gcs upload batch input", f"gs://{BUCKET}/{gcs_in}", "success")

    job = gemini.batches.create(
        model=MODEL, src=f"gs://{BUCKET}/{gcs_in}",
        config={"display_name": f"{cfg['engagement_ref']}-pass1-"
                                f"{datetime.now().strftime('%Y%m%d-%H%M')}"})
    with open(JOB_FILE, "w") as f:
        f.write(job.name)
    m.log_command("agent", "gemini.batches.create", job.name, "success")
    print(f"\nSubmitted batch job: {job.name}")
    print("Saved to ~/scanner/batch_job.txt. Close Cloud Shell; "
          "return in 1–24h and run: python check_batch.py")


if __name__ == "__main__":
    main()
