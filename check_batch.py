"""Polls the Batch API job. Run periodically until it succeeds."""
import os
import json

from google import genai

from config import load_config
from manifest import Manifest

JOB_FILE = os.path.expanduser("~/scanner/batch_job.txt")
RESULTS = os.path.expanduser("~/scanner/batch_results.jsonl")

cfg = load_config()
gemini = genai.Client(api_key=os.environ["GEMINI_API_KEY"])


def main():
    m = Manifest.resume_or_start(cfg)
    job_id = open(JOB_FILE).read().strip()
    job = gemini.batches.get(name=job_id)
    state = str(job.state)
    # SDK may stringify as 'JobState.JOB_STATE_SUCCEEDED' or 'JOB_STATE_SUCCEEDED'
    state_tail = state.split(".")[-1]
    print(f"Job: {job_id}\nState: {state}")

    if state_tail == "JOB_STATE_SUCCEEDED":
        dest = job.dest
        # File API src -> result is a downloadable file; GCS src -> gcs_uri
        file_name = getattr(dest, "file_name", None) if dest else None
        gcs_uri = getattr(dest, "gcs_uri", None) if dest else None
        if file_name:
            data = gemini.files.download(file=file_name)
            with open(RESULTS, "wb") as f:
                f.write(data)
            print(f"Results downloaded to {RESULTS}")
            m.log_command("agent", "batch results download (File API)", file_name, "success")
            print("Next: python assemble_catalog.py")
        elif gcs_uri:
            from urllib.parse import urlparse
            from google.cloud import storage
            p = urlparse(gcs_uri)
            storage.Client(project=cfg["gcp"]["project_id"]).bucket(p.netloc).blob(p.path.lstrip("/")).download_to_filename(RESULTS)
            print(f"Results downloaded to {RESULTS}")
            m.log_command("agent", "batch results download (GCS)", gcs_uri, "success")
            print("Next: python assemble_catalog.py")
        else:
            print("Succeeded but no output destination found on the job:")
            print(json.dumps(job.model_dump(), indent=2, default=str)[:2000])
    elif state_tail in ("JOB_STATE_FAILED", "JOB_STATE_CANCELLED", "JOB_STATE_EXPIRED"):
        m.log_command("agent", "batch poll", job_id, "failure")
        print("Job ended in a non-success state:")
        print(json.dumps(job.model_dump(), indent=2, default=str)[:2000])
    else:
        print("Still running. Check again in 30–60 min.")


if __name__ == "__main__":
    main()
