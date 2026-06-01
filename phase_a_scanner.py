"""
Phase A — Drive API inventory. Config-driven. Emits manifest data_scope.
No file content downloaded — metadata only.
"""
import os
import json
import time
from datetime import datetime, timezone
from collections import Counter

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.cloud import storage
from tqdm import tqdm

from config import load_config
from manifest import Manifest

OUT_LOCAL = os.path.expanduser("~/scanner/phase_a_inventory.jsonl")
GCS_PATH = "pass1/phase_a_inventory.jsonl"


def format_bucket(mime: str) -> str:
    if mime == "application/pdf":
        return "PDF"
    if mime in ("application/msword",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.template"):
        return "Word"
    if mime in ("application/vnd.ms-excel",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "text/csv"):
        return "Excel"
    if mime.startswith("image/"):
        return "Image"
    if mime in ("message/rfc822", "application/vnd.ms-outlook"):
        return "Email"
    if mime.startswith("text/"):
        return "Text"
    if mime == "application/vnd.google-apps.folder":
        return "FOLDER"
    if mime.startswith("application/vnd.google-apps"):
        return "GoogleNative"
    return "Other"


def skip_reason(size: int):
    if size < 1024:
        return "too_small"
    if size > 52_428_800:
        return "too_large"
    return None


def main():
    cfg = load_config()
    m = Manifest.resume_or_start(cfg)
    folder_name = cfg["drive"]["source_folder"]
    bucket_name = cfg["gcp"]["bucket"]

    creds = service_account.Credentials.from_service_account_file(
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"],
        scopes=["https://www.googleapis.com/auth/drive.readonly"])
    drive = build("drive", "v3", credentials=creds)

    res = drive.files().list(
        q=f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder'",
        fields="files(id, name)", pageSize=10).execute()
    folders = res.get("files", [])
    if not folders:
        m.log_command("agent", "drive.files.list (locate folder)", folder_name, "failure")
        raise SystemExit(f"Folder '{folder_name}' not found. Shared with the SA?")
    root_id = folders[0]["id"]
    print(f"Found {folder_name} (id: {root_id})")
    m.log_command("agent", "drive.files.list (locate folder)", folder_name, "success")

    queue = [(root_id, folder_name)]
    records, exclusion = [], Counter()
    pbar = tqdm(desc="Walking Drive", unit="files")
    while queue:
        fid, fpath = queue.pop(0)
        token = None
        while True:
            try:
                resp = drive.files().list(
                    q=f"'{fid}' in parents and trashed=false",
                    fields="nextPageToken, files(id, name, mimeType, size, modifiedTime)",
                    pageToken=token, pageSize=1000).execute()
            except HttpError as e:
                if e.resp.status == 429:
                    time.sleep(5)
                    continue
                raise
            for f in resp.get("files", []):
                if f["mimeType"] == "application/vnd.google-apps.folder":
                    queue.append((f["id"], f"{fpath}/{f['name']}"))
                    continue
                size = int(f.get("size", 0))
                sr = skip_reason(size)
                fb = format_bucket(f["mimeType"])
                if sr:
                    exclusion[sr] += 1
                elif fb in ("GoogleNative", "FOLDER", "Other"):
                    exclusion[f"format_{fb.lower()}"] += 1
                records.append({
                    "drive_id": f["id"], "filepath": f"{fpath}/{f['name']}",
                    "filename": f["name"], "mime_type": f["mimeType"],
                    "format_bucket": fb, "size_bytes": size,
                    "modified_time": f.get("modifiedTime"), "skip_reason": sr,
                    "phase_a_timestamp": datetime.now(timezone.utc).isoformat()})
                pbar.update(1)
            token = resp.get("nextPageToken")
            if not token:
                break
    pbar.close()

    with open(OUT_LOCAL, "w") as out:
        for r in records:
            out.write(json.dumps(r) + "\n")
    print(f"Wrote {len(records)} records to {OUT_LOCAL}")
    m.log_command("agent", "write phase_a_inventory.jsonl", OUT_LOCAL, "success")

    in_scope = sum(1 for r in records
                   if r["skip_reason"] is None
                   and r["format_bucket"] in ("PDF", "Word", "Excel", "Email"))
    m.set_data_scope(source_folder=folder_name, files_discovered=len(records),
                     files_in_scope=in_scope, exclusion_reasons=dict(exclusion),
                     pass_scope="pass1_type_only", pii_persisted=False)

    print("\n=== Phase A Summary ===")
    for b, c in Counter(r["format_bucket"] for r in records).most_common():
        print(f"  {b}: {c}")
    print(f"\nIn scope for Phase B: {in_scope}")

    storage.Client().bucket(bucket_name).blob(GCS_PATH).upload_from_filename(OUT_LOCAL)
    print(f"\nUploaded to gs://{bucket_name}/{GCS_PATH}")
    m.log_command("agent", "gcs upload", f"gs://{bucket_name}/{GCS_PATH}", "success")


if __name__ == "__main__":
    main()
