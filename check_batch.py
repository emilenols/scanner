"""Polls the Batch API job. Run periodically until it succeeds."""
import os
import json
from urllib.parse import urlparse

from google import genai
from google.cloud import storage

from config import load_config
from manifest import Manifest

JOB_FILE = os.path.expanduser("~/scanner/batch_job.txt")
RESULTS = os.path.expanduser("~/scanner/batch_results.jsonl")

cfg = load_config()
gemini = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
gcs = storage.Client()


def main():
    m = Manifest.resume_or_start(cfg)
    job_id = open(JOB_FILE).read().strip()
    job = gemini.batches.get(name=job_id)
    print(f"Job: {job_id}\nState: {job.state}")

    state = str(job.state)
    if state == "JOB_STATE_SUCCEEDED":
        out_uri = job.dest.gcs_uri if job.dest else None
        print(f"Complete. Output: {out_uri}")
        if out_uri:
            p = urlparse(out_uri)
            gcs.bucket(p.netloc).blob(p.path.lstrip("/")).download_to_filename(RESULTS)
            print(f"Results downloaded to {RESULTS}")
            m.log_command("agent", "batch results download", out_uri, "success")
            print("Next: python assemble_catalog.py")
    elif state in ("JOB_STATE_FAILED", "JOB_STATE_CANCELLED", "JOB_STATE_EXPIRED"):
        m.log_command("agent", "batch poll", job_id, "failure")
        print("Job ended in non-success state:")
        print(json.dumps(job.model_dump(), indent=2, default=str))
    else:
        print("Still running. Check again in 30–60 min.")


if __name__ == "__main__":
    main()
