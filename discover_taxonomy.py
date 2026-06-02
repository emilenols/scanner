"""
discover_taxonomy.py — analyse the drive and propose a taxonomy FROM the documents.

This is the centerpiece "Drive Analysis" step. It runs after phase_a_scanner.py
and before pilot_scanner.py. It samples real documents, asks the model
(open-ended, NO fixed list) what each one is + how confident + whether it is a
clean file or a poor scan, then produces a client-facing report:

  drive_analysis.md            — ranked types, folder breakdown, scan-quality
                                 warning, corpus estimates, paste-ready taxonomy
  drive_analysis_sample.csv    — per-document detail for spot-checking

The operator reviews drive_analysis.md, edits the proposed taxonomy, and pastes
the approved list into client_config.yaml. That review is Gate A.

Why this exists: you cannot create a bin for a document type you've forgotten
exists. This lets the drive reveal what's actually on it — the first step in
turning an unstructured archive into an AI-ready, queryable catalog.

  python discover_taxonomy.py            # samples 120 docs
  python discover_taxonomy.py --sample 200
"""
import argparse
import io
import json
import os
import random
import statistics
from collections import Counter, defaultdict

from pydantic import BaseModel

import reader

INV = os.path.expanduser("~/scanner/phase_a_inventory.jsonl")
REPORT_MD = os.path.expanduser("~/scanner/drive_analysis.md")
SAMPLE_CSV = os.path.expanduser("~/scanner/drive_analysis_sample.csv")
DEFAULT_SAMPLE = 120
SEED = 42
ILLEGIBLE_WARN = 20.0   # % poor scans that triggers a warning
LOWCONF_WARN = 25.0     # % low-confidence that triggers a warning


class DocObservation(BaseModel):
    type_label: str   # 2-4 words, free text
    family: str       # legal / financial / correspondence / technical / identity / other
    confidence: float # 0-1: certainty about the type
    legible: bool     # True = clean/readable; False = poor scan / garbled
    reason: str


class ProposedType(BaseModel):
    canonical: str
    merged_from: list[str]


class TaxonomyProposal(BaseModel):
    types: list[ProposedType]


def _norm(s: str) -> str:
    return " ".join(str(s).lower().strip().split())


def _subfolder(filepath: str) -> str:
    parts = [p for p in str(filepath).split("/") if p]
    return parts[1] if len(parts) >= 3 else "(root)"


def render_report(per_doc, proposed, cfg, total_eligible):
    """Pure (no network) — builds the Drive Analysis markdown, paste-ready YAML,
    and per-doc CSV. Factored out so it is unit-testable."""
    n = len(per_doc) or 1
    # raw label -> canonical map
    raw2canon = {}
    for t in proposed:
        for raw in t.get("merged_from", []):
            raw2canon[_norm(raw)] = t["canonical"]

    def canon_of(d):
        return raw2canon.get(_norm(d["type_label"]), "Unknown")

    # per-type aggregation from the sample (more accurate than any LLM estimate)
    by_type_docs = defaultdict(list)
    for d in per_doc:
        by_type_docs[canon_of(d)].append(d)
    examples = defaultdict(list)
    for d in per_doc:
        examples[_norm(d["type_label"])].append(d["filename"])

    # order: by sample count desc, Unknown always last
    ordered = sorted({t["canonical"] for t in proposed},
                     key=lambda c: (c.lower() == "unknown", -len(by_type_docs.get(c, []))))

    # scan-quality + confidence signals
    illegible_pct = 100 * sum(1 for d in per_doc if not d.get("legible", True)) / n
    lowconf_pct = 100 * sum(1 for d in per_doc if d.get("confidence", 1) < 0.6) / n
    mean_conf = statistics.mean([d.get("confidence", 0) for d in per_doc]) if per_doc else 0

    md = [f"# Drive Analysis — {cfg.get('client','(client)')}",
          f"_Based on a sample of **{len(per_doc)}** of ~{total_eligible} eligible "
          f"documents (PDF/Word) in `{cfg.get('drive',{}).get('source_folder','the drive')}`._\n",
          "## Summary",
          f"- **Eligible documents in drive:** ~{total_eligible}",
          f"- **Sample analysed:** {len(per_doc)}",
          f"- **Distinct document types found:** {len(ordered)}",
          f"- **Average classification confidence:** {mean_conf:.2f}",
          f"- **Clean / readable:** {100-illegible_pct:.0f}%  ·  "
          f"**Poor scans / hard to read:** {illegible_pct:.0f}%"]

    if illegible_pct >= ILLEGIBLE_WARN or lowconf_pct >= LOWCONF_WARN:
        md.append("\n> **⚠ Scan-quality note:** "
                  f"{illegible_pct:.0f}% of the sample looks like poor scans and "
                  f"{lowconf_pct:.0f}% classified with low confidence. Expect a "
                  "higher review rate; consider the stronger model before the full "
                  "run, and flag to your advisor.")

    md += ["\n## Document types found (ranked)",
           "| # | Type | Share of sample | Est. in drive | Avg. confidence | Example files |",
           "|---|---|---|---|---|---|"]
    yaml_lines = ["  document_types:"]
    for i, c in enumerate(ordered, 1):
        docs = by_type_docs.get(c, [])
        share = 100 * len(docs) / n
        est = round(share / 100 * total_eligible)
        conf = statistics.mean([d.get("confidence", 0) for d in docs]) if docs else 0
        ex = []
        for t in proposed:
            if t["canonical"] == c:
                for raw in t.get("merged_from", []):
                    ex.extend(examples.get(_norm(raw), []))
        ex_str = "; ".join(ex[:3]) if ex else "—"
        md.append(f"| {i} | **{c}** | {share:.0f}% | ~{est} | {conf:.2f} | {ex_str} |")
        yaml_lines.append(f'    - "{c}"')

    # folder breakdown
    by_folder = defaultdict(list)
    for d in per_doc:
        by_folder[_subfolder(d.get("filepath", ""))].append(canon_of(d))
    md += ["\n## Where they live (top-level folders in the sample)",
           "| Folder | Docs in sample | Most common types |",
           "|---|---|---|"]
    for folder, canons in sorted(by_folder.items(), key=lambda kv: -len(kv[1])):
        top = ", ".join(f"{t} ({c})" for t, c in Counter(canons).most_common(3))
        md.append(f"| `{folder}` | {len(canons)} | {top} |")

    md += ["\n## Recommended taxonomy",
           "Edit the names below (rename, merge, drop, add anything the sample "
           "missed), then paste into `client_config.yaml` -> `taxonomy.document_types`. "
           "Keep `Unknown` last. **This edited list is your Gate A.**\n",
           "```yaml"]
    md += yaml_lines
    md += ["```",
           "\n**How to read this:**",
           "- High-share types are safe to keep. Rare types (1–2 docs) — decide "
           "consciously: own bin, or fold into a neighbour. Anything you drop gets "
           "filed into the nearest remaining bin.",
           "- A low average confidence or a high poor-scan share means the archive "
           "is messy — that is normal for old drives, and it is exactly what the "
           "full scan + review queue is built to handle.\n",
           "_This is a sample-based survey, not the final catalog. The full Pass 1 "
           "scan classifies every document and produces the catalog._"]

    csv_rows = ["filename,folder,raw_type_label,canonical_type,family,confidence,legible,reason"]
    for d in per_doc:
        r = str(d.get("reason", "")).replace('"', "'").replace("\n", " ")
        csv_rows.append(
            f'"{d["filename"]}","{_subfolder(d.get("filepath",""))}",'
            f'"{d["type_label"]}","{canon_of(d)}","{d.get("family","")}",'
            f'{d.get("confidence","")},{d.get("legible","")},"{r}"')
    return "\n".join(md), "\n".join(yaml_lines), "\n".join(csv_rows)


def _run(sample_n):
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload
    from google import genai
    from google.genai import types
    from tqdm import tqdm
    from tenacity import retry, stop_after_attempt, wait_exponential
    from config import load_config, routing, verify_model
    from manifest import Manifest

    cfg = load_config()
    m = Manifest.resume_or_start(cfg)
    model = routing(cfg)["model"]
    sys_ctx = cfg["taxonomy"].get("system_context", "document repository")

    creds = service_account.Credentials.from_service_account_file(
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"],
        scopes=["https://www.googleapis.com/auth/drive.readonly"])
    drive = build("drive", "v3", credentials=creds)
    gemini = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    verify_model(gemini, model)

    include_images = cfg.get("scan", {}).get("include_images", True)
    with open(INV) as f:
        inv = [json.loads(l) for l in f]
    cand = [r for r in inv if reader.is_eligible(r, include_images)]
    if not cand:
        raise SystemExit("No eligible PDF/Word files. Run phase_a_scanner.py first.")
    total_eligible = len(cand)
    random.seed(SEED)
    sample = random.sample(cand, min(sample_n, total_eligible))
    print(f"Analysing {len(sample)} of {total_eligible} eligible documents")

    open_sys = (
        f"You are surveying a document repository for a {sys_ctx}. For the "
        "document, name its type in 2-4 words as a business person would (e.g. "
        "'lease agreement', 'rent roll', 'utility invoice'). Do NOT use a fixed "
        "list. Give a one-word family (legal, financial, correspondence, "
        "technical, identity, other), a confidence 0-1 for your type label, "
        "whether the document is legible (true) or a poor/garbled scan (false), "
        "and a one-sentence reason.")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=20))
    def observe(result):
        resp = gemini.models.generate_content(
            model=model,
            contents=reader.sync_contents(result, "Describe this document per the instructions."),
            config=types.GenerateContentConfig(
                system_instruction=open_sys, response_mime_type="application/json",
                response_schema=DocObservation, temperature=0.2))
        return json.loads(resp.text)

    per_doc, skips = [], Counter()
    for r in tqdm(sample, desc="Analysing drive"):
        try:
            result = reader.read_for_model(drive, r, include_images)
        except reader.UnreadableDocument as e:
            skips[e.reason] += 1
            continue
        try:
            o = observe(result)
            per_doc.append({"filename": r["filename"], "filepath": r["filepath"], **o})
        except Exception as e:
            skips["model_error"] += 1
            print(f"  skip {r['filename']}: {str(e)[:80]}")
    if skips:
        print("Skipped (not analysed):", dict(skips))

    counts = Counter(_norm(d["type_label"]) for d in per_doc)
    label_summary = "\n".join(f"- {lbl}: {c}" for lbl, c in counts.most_common())
    consolidate_sys = (
        f"These document-type labels were observed in a sample from a {sys_ctx}, "
        "with counts. Consolidate synonyms/near-duplicates into a clean, "
        "non-overlapping taxonomy of 8 to 15 canonical types. Merge variants "
        "(e.g. 'lease','lease agreement' -> 'Lease Agreement'). Always include "
        "'Unknown'. In merged_from list the raw labels folded into each type.")
    try:
        resp = gemini.models.generate_content(
            model=model, contents=[f"Labels with counts:\n{label_summary}"],
            config=types.GenerateContentConfig(
                system_instruction=consolidate_sys,
                response_mime_type="application/json",
                response_schema=TaxonomyProposal, temperature=0.1))
        proposed = json.loads(resp.text)["types"]
    except Exception as e:
        print(f"  consolidation failed ({e}); using raw frequency list")
        proposed = [{"canonical": lbl.title(), "merged_from": [lbl]}
                    for lbl, _c in counts.most_common(14)]
        if not any(p["canonical"].lower() == "unknown" for p in proposed):
            proposed.append({"canonical": "Unknown", "merged_from": []})

    md, _yaml, csv = render_report(per_doc, proposed, cfg, total_eligible)
    with open(REPORT_MD, "w") as f:
        f.write(md)
    with open(SAMPLE_CSV, "w") as f:
        f.write(csv)
    m.log_command("agent", f"drive analysis / taxonomy discovery "
                  f"({len(per_doc)} of {total_eligible} sampled, "
                  f"{len(proposed)} types proposed)", "phase_a_inventory", "success")

    print(f"\nDrive Analysis report:\n  {REPORT_MD}")
    print(f"Per-document detail:\n  {SAMPLE_CSV}")
    print("\nNext: read drive_analysis.md, edit the proposed taxonomy, paste the "
          "approved list into client_config.yaml -> taxonomy.document_types "
          "(this is Gate A). Then run pilot_scanner.py.")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--sample", type=int, default=DEFAULT_SAMPLE)
    _run(p.parse_args().sample)


if __name__ == "__main__":
    main()
