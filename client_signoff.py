"""
client_signoff.py — record the CLIENT's review as a real action.

Run AFTER assemble_catalog.py, once the named client approver has actually
reviewed the catalog. This stamps a real name + timestamp into the manifest
(not a config echo), logs it to the audit trail, re-uploads the manifest, and
re-renders the attestation so the document shows a genuine countersignature.

  python client_signoff.py --approver "Lloyd Verbeeck" \
      --role "Director, Lease Estate" --confirm
"""
import argparse
import os
import subprocess
import sys

from config import load_config
from manifest import Manifest


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--approver", required=True)
    p.add_argument("--role", required=True)
    p.add_argument("--notes", default="")
    p.add_argument("--confirm", action="store_true",
                   help="Attest that the named approver has reviewed the catalog.")
    a = p.parse_args()
    if not a.confirm:
        sys.exit("Add --confirm to attest the named approver has reviewed the catalog.")

    cfg = load_config()
    m = Manifest.resume_or_start(cfg)
    if m.m.attestation is None:
        sys.exit("Operator attestation missing — run assemble_catalog.py first.")

    m.attest_client(a.approver)
    action = "client sign-off" + (f" — {a.notes}" if a.notes else "")
    m.log_command("human", action, f"{a.approver} ({a.role})", "success")
    print(f"Client sign-off recorded: {a.approver} ({a.role})")

    try:
        m.upload_gcs(cfg["gcp"]["bucket"])
        print("Manifest re-uploaded.")
    except Exception as ex:
        print(f"(skip manifest upload: {ex})")

    try:
        here = os.path.dirname(os.path.abspath(__file__))
        subprocess.run([sys.executable,
                        os.path.join(here, "render_compliance_summary.py")],
                       check=False)
    except Exception as ex:
        print(f"(skip re-render: {ex})")


if __name__ == "__main__":
    main()
