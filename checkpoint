#!/usr/bin/env python3
"""
checkpoint.py — produce a SAFE, redacted status report to send to Focusfinder.

Run at a checkpoint (or when something breaks) and send Emile the file it writes.
The report contains AGGREGATE METADATA ONLY — counts, type categories, confidence
statistics, error reasons, hashes. It NEVER contains document content, file names,
folder names, or model reasoning, so it is safe to share outside your tenant.

  python checkpoint.py doctor       # environment + state snapshot (use when stuck)
  python checkpoint.py inventory    # after phase_a_scanner.py
  python checkpoint.py discovery    # after discover_taxonomy.py
  python checkpoint.py pilot        # after pilot_scanner.py
  python checkpoint.py catalog      # after assemble_catalog.py
"""
import os
import sys
import csv
import json
import glob
from collections import Counter

HOME = os.path.expanduser("~/scanner")
SAFE_HEADER = (
    "SAFE TO SHARE: aggregate metadata only — no document content, file names, "
    "folder names, or model reasoning. Specific files are referenced by opaque "
    "Drive ID only.\n")


def _load_jsonl(name):
    p = os.path.join(HOME, name)
    if not os.path.exists(p):
        return None
    return [json.loads(l) for l in open(p) if l.strip()]


def _conf_hist(vals):
    bins = {"<0.50": 0, "0.50–0.70": 0, "0.70–0.85": 0, "≥0.85": 0}
    for v in vals:
        if v < 0.5: bins["<0.50"] += 1
        elif v < 0.7: bins["0.50–0.70"] += 1
        elif v < 0.85: bins["0.70–0.85"] += 1
        else: bins["≥0.85"] += 1
    return bins


def _section(title, lines):
    return [f"## {title}"] + lines + [""]


def doctor():
    out = ["# Checkpoint: DOCTOR (environment & state)", "", SAFE_HEADER]
    env = []
    env.append(f"GEMINI_API_KEY set: {'yes' if os.environ.get('GEMINI_API_KEY') else 'NO'}")
    cred = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
    env.append(f"Service-account key set: {'yes' if cred and os.path.exists(cred) else 'NO'}")
    try:
        import subprocess
        proj = subprocess.run(["gcloud", "config", "get-value", "project"],
                              capture_output=True, text=True, timeout=15).stdout.strip()
        env.append(f"Active gcloud project: {proj or '(unset)'}")
    except Exception:
        env.append("Active gcloud project: (could not read)")
    out += _section("Environment", env)

    cfg_state = []
    cpath = os.path.join(HOME, "client_config.yaml")
    if os.path.exists(cpath):
        try:
            import yaml
            c = yaml.safe_load(open(cpath))
            cfg_state.append(f"client / engagement: {c.get('client')} / {c.get('engagement_ref')}")
            cfg_state.append(f"region: {c.get('gcp', {}).get('region')}")
            cfg_state.append(f"model: {c.get('routing', {}).get('model')}")
            cfg_state.append(f"document_types: {len(c.get('taxonomy', {}).get('document_types', []))} "
                             f"-> {c.get('taxonomy', {}).get('document_types')}")
            cfg_state.append(f"include_images: {c.get('scan', {}).get('include_images')}")
            cfg_state.append(f"pass2_legal_basis_ref: {c.get('gdpr', {}).get('pass2_legal_basis_ref')}")
        except Exception as e:
            cfg_state.append(f"config present but unreadable: {str(e)[:80]}")
    else:
        cfg_state.append("client_config.yaml: NOT FOUND")
    out += _section("Config (no secrets)", cfg_state)

    files = []
    for f in sorted(glob.glob(os.path.join(HOME, "*"))):
        b = os.path.basename(f)
        if b in ("venv", "client_config.yaml", "__pycache__") or b.endswith(".py"):
            continue
        if os.path.isfile(f):
            files.append(f"{b}: {os.path.getsize(f)//1024} KB")
    out += _section("Artifacts present", files or ["(none yet)"])

    pkgs = []
    try:
        from importlib.metadata import version
        for p in ("google-genai", "google-cloud-storage", "python-docx", "openpyxl", "pandas"):
            try: pkgs.append(f"{p}: {version(p)}")
            except Exception: pkgs.append(f"{p}: not installed")
    except Exception:
        pass
    out += _section("Key package versions", pkgs)
    out.append("If you hit an error, also paste the LAST ~15 lines of the red error text.")
    return "\n".join(out)


def inventory():
    inv = _load_jsonl("phase_a_inventory.jsonl")
    if not inv:
        return "No phase_a_inventory.jsonl yet — run phase_a_scanner.py first."
    try:
        import reader
        cfg_inc = True
        cpath = os.path.join(HOME, "client_config.yaml")
        if os.path.exists(cpath):
            import yaml
            cfg_inc = yaml.safe_load(open(cpath)).get("scan", {}).get("include_images", True)
        eligible = sum(1 for r in inv if reader.is_eligible(r, cfg_inc))
    except Exception:
        eligible = "?"
    buckets = Counter(r.get("format_bucket") for r in inv)
    skips = Counter(r.get("skip_reason") for r in inv if r.get("skip_reason"))
    sizes = sorted(r.get("size_bytes", 0) for r in inv)
    big = sum(1 for s in sizes if s > 10 * 1024 * 1024)
    folders = len({(r.get("filepath", "").split("/") or [""])[1]
                   for r in inv if r.get("filepath", "").count("/") >= 2})
    out = ["# Checkpoint: INVENTORY", "", SAFE_HEADER]
    out += _section("Totals", [
        f"files walked: {len(inv)}",
        f"eligible for processing: {eligible}",
        f"top-level folders: ~{folders}",
        f"files over 10 MB: {big}"])
    out += _section("By format", [f"{k}: {v}" for k, v in buckets.most_common()])
    out += _section("Skip reasons (Phase A)", [f"{k}: {v}" for k, v in skips.most_common()] or ["(none)"])
    return "\n".join(out)


def discovery():
    out = ["# Checkpoint: DISCOVERY / taxonomy", "", SAFE_HEADER]
    tpath = os.path.join(HOME, "proposed_taxonomy.txt")
    if os.path.exists(tpath):
        types = [l.strip() for l in open(tpath) if l.strip() and not l.startswith("#")]
        out += _section("Proposed taxonomy (category names only)", [f"- {t}" for t in types])
    spath = os.path.join(HOME, "drive_analysis_sample.csv")
    if os.path.exists(spath):
        rows = list(csv.DictReader(open(spath)))
        fams = Counter(r.get("family", "") for r in rows)
        confs = [float(r["confidence"]) for r in rows if r.get("confidence", "").replace(".", "", 1).isdigit()]
        legible_no = sum(1 for r in rows if str(r.get("legible", "")).lower() == "false")
        out += _section("Sample stats", [
            f"documents sampled: {len(rows)}",
            f"poor-scan / illegible: {legible_no} ({100*legible_no/max(len(rows),1):.0f}%)"])
        out += _section("Family distribution", [f"{k}: {v}" for k, v in fams.most_common()])
        if confs:
            out += _section("Confidence", [
                f"mean: {sum(confs)/len(confs):.2f}",
                *[f"{k}: {v}" for k, v in _conf_hist(confs).items()]])
    if len(out) <= 3:
        return "No discovery artifacts yet — run discover_taxonomy.py first."
    return "\n".join(out)


def _catalog_report(rows, title, fail_rows=None):
    out = [f"# Checkpoint: {title}", "", SAFE_HEADER]
    confs = [float(r.get("confidence", 0)) for r in rows]
    review = sum(1 for r in rows if r.get("review_required"))
    types = Counter(r.get("document_type") for r in rows)
    out += _section("Totals", [
        f"classified: {len(rows)}",
        f"flagged for review: {review} ({100*review/max(len(rows),1):.1f}%)"])
    out += _section("Type distribution", [f"{k}: {v}" for k, v in types.most_common()])
    if confs:
        out += _section("Confidence", [
            f"mean: {sum(confs)/len(confs):.2f}",
            *[f"{k}: {v}" for k, v in _conf_hist(confs).items()]])
    if fail_rows:
        reasons = Counter((r.get("error", "")[:40]) for r in fail_rows)
        out += _section("Failures (by reason)", [f"{k}: {v}" for k, v in reasons.most_common()])
        ids = [r.get("drive_id", "?") for r in fail_rows][:25]
        out += _section("Failed Drive IDs (opaque, for your lookup)", ids or ["(none)"])
    return "\n".join(out)


def pilot():
    rows = _load_jsonl("pilot_catalog.jsonl")
    if not rows:
        return "No pilot_catalog.jsonl yet — run pilot_scanner.py first."
    return _catalog_report(rows, "PILOT", _load_jsonl("pilot_failures.jsonl"))


def catalog():
    rows = _load_jsonl("catalog_v1.jsonl")
    if not rows:
        return "No catalog_v1.jsonl yet — run assemble_catalog.py first."
    return _catalog_report(rows, "FINAL CATALOG")


STEPS = {"doctor": doctor, "inventory": inventory, "discovery": discovery,
         "pilot": pilot, "catalog": catalog}


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in STEPS:
        print("Usage: python checkpoint.py [doctor|inventory|discovery|pilot|catalog]")
        sys.exit(1)
    step = sys.argv[1]
    report = STEPS[step]()
    path = os.path.join(HOME, f"checkpoint_{step}.md")
    with open(path, "w") as f:
        f.write(report + "\n")
    print(report)
    print("\n" + "=" * 60)
    print(f"Saved to {path}")
    print("Send this file (or paste the text above) to Emile. It is safe to share:")
    print("it contains no document content, file names, or folder names.")


if __name__ == "__main__":
    main()
