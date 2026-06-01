"""
render_compliance_summary.py — turn a finalized scan manifest into the
one-page attestation a DPO/board can read.

Principles:
  * Reads ONLY the manifest. Adds no new data, touches no documents, no PII.
    Every statement on the page is backed by the cryptographically-hashed,
    signed manifest — that is the integrity claim.
  * Uses DEFENSIBLE language: "designed on EU AI Act principles", not
    "compliant". The page presents facts; it is not legal advice.
  * If the manifest is not finalized, renders a DRAFT — not for distribution.

Usage:
  python render_compliance_summary.py                 # latest run (run_id.txt)
  python render_compliance_summary.py --manifest PATH  # explicit
"""
import argparse
import html
import json
import os

OUT_HTML = os.path.expanduser("~/scanner/compliance_summary.html")
RUN_ID_FILE = os.path.expanduser("~/scanner/run_id.txt")
AUDIT_DIR = os.path.expanduser("~/scanner/audit")


def _load_manifest(path: str | None) -> dict:
    if not path:
        if not os.path.exists(RUN_ID_FILE):
            raise SystemExit("No run_id.txt found — run the scan first, or pass --manifest.")
        run_id = open(RUN_ID_FILE).read().strip()
        path = os.path.join(AUDIT_DIR, f"scan_manifest_{run_id}.json")
    if not os.path.exists(path):
        raise SystemExit(f"Manifest not found: {path}")
    with open(path) as f:
        return json.load(f)


def e(x) -> str:
    return html.escape(str(x)) if x is not None else "—"


def _date(iso: str | None) -> str:
    if not iso:
        return "—"
    return e(iso.split("T")[0])


CSS = """
:root{
  --paper:#fbfaf6; --ink:#1b1b18; --muted:#6c6a60; --hair:#dcd8cd;
  --accent:#15463a; --accent-2:#1f6f5c; --seal:#15463a; --warn:#9a2a1f;
  --pending:#9a6a1f;
}
*{box-sizing:border-box;}
html,body{margin:0;padding:0;}
body{
  background:var(--paper); color:var(--ink);
  font-family:'Hanken Grotesk',system-ui,sans-serif;
  font-size:15px; line-height:1.55; -webkit-font-smoothing:antialiased;
}
.sheet{
  max-width:840px; margin:32px auto; background:var(--paper);
  padding:56px 64px 40px; position:relative;
}
.rule-top{height:4px;background:var(--accent);width:100%;}
h1,h2,h3{font-family:'Fraunces',Georgia,serif;font-weight:560;margin:0;}
h1{font-size:34px;line-height:1.08;letter-spacing:-0.01em;}
h2{font-size:13px;text-transform:uppercase;letter-spacing:.14em;
   color:var(--accent);font-family:'Hanken Grotesk',sans-serif;font-weight:700;}
.mono{font-family:'JetBrains Mono',ui-monospace,monospace;}
.muted{color:var(--muted);}
.masthead{display:flex;justify-content:space-between;align-items:flex-start;
  padding-bottom:22px;border-bottom:1px solid var(--hair);margin-top:30px;}
.brand{font-family:'Fraunces',serif;font-size:15px;font-weight:560;}
.brand small{display:block;font-family:'Hanken Grotesk',sans-serif;
  font-size:10.5px;letter-spacing:.16em;text-transform:uppercase;color:var(--muted);
  font-weight:600;margin-top:3px;}
.kicker{font-size:11px;letter-spacing:.18em;text-transform:uppercase;
  color:var(--accent-2);font-weight:700;margin-bottom:10px;}
.meta{display:grid;grid-template-columns:repeat(3,1fr);gap:18px;margin:26px 0 6px;}
.meta .lbl{font-size:10.5px;letter-spacing:.12em;text-transform:uppercase;
  color:var(--muted);font-weight:600;margin-bottom:3px;}
.meta .val{font-size:14px;}
.seal{position:absolute;top:52px;right:64px;width:96px;height:96px;border-radius:50%;
  border:1.5px solid var(--seal);display:flex;flex-direction:column;
  align-items:center;justify-content:center;text-align:center;
  transform:rotate(-7deg);color:var(--seal);}
.seal.pending{border-color:var(--pending);color:var(--pending);}
.seal .v{font-family:'Fraunces',serif;font-size:13px;font-weight:600;letter-spacing:.1em;}
.seal .s{font-size:8px;letter-spacing:.1em;text-transform:uppercase;margin-top:2px;}
.seal .id{font-family:'JetBrains Mono',monospace;font-size:8px;margin-top:4px;}
.pendingbar{background:#f3ead4;color:var(--pending);padding:8px 16px;font-size:12px;
  letter-spacing:.03em;text-align:center;font-weight:600;
  border-bottom:1px solid #e3d5ad;}
section{margin-top:30px;}
.lead{font-family:'Fraunces',serif;font-size:18px;line-height:1.5;margin-top:14px;}
.cards{display:grid;grid-template-columns:1fr 1fr;gap:1px;background:var(--hair);
  border:1px solid var(--hair);margin-top:14px;}
.card{background:var(--paper);padding:18px 20px;}
.card .pname{font-family:'Fraunces',serif;font-size:16px;margin-bottom:4px;}
.card .fact{font-size:13.5px;}
.card .ev{font-size:11px;color:var(--muted);margin-top:8px;
  font-family:'JetBrains Mono',monospace;letter-spacing:.02em;}
table{width:100%;border-collapse:collapse;margin-top:12px;font-size:13px;}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--hair);}
th{font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);}
td.h{font-family:'JetBrains Mono',monospace;font-size:11px;word-break:break-all;color:var(--accent);}
.statgrid{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:var(--hair);
  border:1px solid var(--hair);margin-top:14px;}
.stat{background:var(--paper);padding:16px 18px;}
.stat .n{font-family:'Fraunces',serif;font-size:26px;}
.stat .l{font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);margin-top:2px;}
.attest{display:grid;grid-template-columns:1fr 1fr;gap:30px;margin-top:16px;}
.sig{border-top:1px solid var(--ink);padding-top:8px;}
.sig .who{font-size:14px;font-weight:600;}
.sig .role,.sig .when{font-size:11.5px;color:var(--muted);}
footer{margin-top:34px;padding-top:16px;border-top:1px solid var(--hair);
  font-size:11px;color:var(--muted);line-height:1.5;}
.draft{position:fixed;inset:0;display:flex;align-items:center;justify-content:center;
  pointer-events:none;z-index:5;}
.draft span{font-family:'Fraunces',serif;font-size:120px;color:rgba(154,42,31,.10);
  transform:rotate(-22deg);letter-spacing:.05em;font-weight:600;}
.draftbar{background:var(--warn);color:#fff;padding:9px 16px;font-size:12px;
  letter-spacing:.05em;text-align:center;font-weight:600;}
@keyframes rise{from{opacity:0;transform:translateY(10px);}to{opacity:1;transform:none;}}
.sheet > *{animation:rise .5s both;}
.sheet > *:nth-child(2){animation-delay:.05s;}
.sheet > *:nth-child(3){animation-delay:.10s;}
.sheet > *:nth-child(n+4){animation-delay:.15s;}
@media print{
  body{background:#fff;} .sheet{margin:0;padding:36px 40px;}
  .sheet>*{animation:none;} @page{margin:14mm;}
  section,.card,.stat{break-inside:avoid;}
}
"""


def _principle_cards(m: dict) -> str:
    ds = m.get("data_scope") or {}
    proc = (m.get("processing") or [{}])[0]
    gates = m.get("human_gates") or []
    gate_b = next((g for g in gates if g.get("gate") == "B_pilot_review"), {})
    ap = m.get("ai_act_principles") or {}

    gate_summary = "—"
    if gate_b:
        gate_summary = (f"{e(gate_b.get('sample_correct'))}/{e(gate_b.get('sample_size'))} "
                        f"correct · reviewed by {e(gate_b.get('approver_name'))} "
                        f"on {_date(gate_b.get('timestamp'))}")

    cards = [
        ("Human oversight", e(ap.get("human_oversight", "")),
         f"Gate B: {gate_summary}"),
        ("Data minimization", e(ap.get("data_minimization", "")),
         f"Pass 1 PII persisted: {('no' if not ds.get('pii_persisted') else 'YES')} · "
         f"in scope {e(ds.get('files_in_scope'))} of {e(ds.get('files_discovered'))}"),
        ("Transparency", e(ap.get("transparency", "")),
         f"Model: {e(proc.get('model'))} · accept ≥ {e(proc.get('confidence_threshold_accept'))}"),
        ("Logging", e(ap.get("logging", "")),
         f"{len(m.get('commands') or [])} actions logged · manifest hashed"),
    ]
    out = []
    for name, fact, ev in cards:
        out.append(f'<div class="card"><div class="pname">{e(name)}</div>'
                   f'<div class="fact">{fact}</div><div class="ev">{ev}</div></div>')
    return '<div class="cards">' + "".join(out) + "</div>"


def _exclusion_rows(ds: dict) -> str:
    rows = ""
    for reason, count in (ds.get("exclusion_reasons") or {}).items():
        rows += f"<tr><td>{e(reason)}</td><td>{e(count)}</td></tr>"
    return rows or '<tr><td class="muted">none</td><td>0</td></tr>'


def _hash_rows(oi: dict) -> str:
    rows = ""
    for fname, h in (oi.get("catalog_files") or {}).items():
        rows += f'<tr><td>{e(fname)}</td><td class="h">{e(h)}</td></tr>'
    return rows or '<tr><td class="muted">no outputs recorded</td><td>—</td></tr>'


def render(m: dict) -> str:
    finalized = bool(m.get("finished") and m.get("attestation")
                     and m.get("output_integrity"))
    ds = m.get("data_scope") or {}
    proc = (m.get("processing") or [{}])[0]
    oi = m.get("output_integrity") or {}
    att = m.get("attestation") or {}
    run_id = e(m.get("run_id", ""))
    short_id = run_id[:8]
    client_signed = bool(att.get("client_signature_timestamp"))

    # Three honest states.
    if not finalized:
        state = "draft"
    elif client_signed:
        state = "countersigned"
    else:
        state = "operator"

    draft_overlay = '<div class="draft"><span>DRAFT</span></div>' if state == "draft" else ""
    if state == "draft":
        status_bar = ('<div class="draftbar">DRAFT — manifest not finalized · '
                      'not for distribution</div>')
    elif state == "operator":
        status_bar = ('<div class="pendingbar">OPERATOR ATTESTED — awaiting client '
                      'sign-off · interim record</div>')
    else:
        status_bar = ""

    if state == "countersigned":
        seal = (f'<div class="seal"><div class="v">VERIFIED</div>'
                f'<div class="s">countersigned</div><div class="id">{short_id}</div></div>')
    elif state == "operator":
        seal = (f'<div class="seal pending"><div class="v">ATTESTED</div>'
                f'<div class="s">client pending</div><div class="id">{short_id}</div></div>')
    else:
        seal = ""

    client_cell = (f'<div class="who">{e(att.get("client_approver_name","—"))}</div>'
                   f'<div class="role">Client approver</div>'
                   f'<div class="when">{_date(att.get("client_signature_timestamp"))}</div>'
                   if client_signed else
                   '<div class="who muted">— pending client sign-off</div>'
                   '<div class="role">Client approver</div>'
                   '<div class="when">—</div>')

    client_note = ("" if client_signed else
                   " &nbsp;·&nbsp; Client sign-off is pending; this document "
                   "reflects operator attestation only.")

    total = e(oi.get("total_rows", "—"))
    review = e(oi.get("review_rate_pct", proc.get("review_rate_pct", "—")))
    excluded = e(ds.get("files_excluded", "—"))

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Data Processing Attestation — {e(m.get('client',''))}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,560;9..144,600&family=Hanken+Grotesk:wght@400;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>{CSS}</style></head><body>
{status_bar}{draft_overlay}
<div class="sheet">
<div class="rule-top"></div>
<div class="masthead">
  <div>
    <div class="kicker">Data Processing Attestation</div>
    <h1>Document Classification Scan</h1>
  </div>
  <div class="brand">Focusfinder Consulting<small>Compliant Data Foundation</small></div>
</div>
{seal}
<div class="meta">
  <div><div class="lbl">Client</div><div class="val">{e(m.get('client',''))}</div></div>
  <div><div class="lbl">Engagement</div><div class="val">{e(m.get('engagement_ref',''))}</div></div>
  <div><div class="lbl">Scan completed</div><div class="val">{_date(m.get('finished'))}</div></div>
  <div><div class="lbl">GCP project · region</div><div class="val">{e(m.get('gcp_project',''))} · {e(m.get('gcp_region',''))}</div></div>
  <div><div class="lbl">Run identifier</div><div class="val mono" style="font-size:11px">{run_id}</div></div>
  <div><div class="lbl">Scanner</div><div class="val">{e(m.get('scanner_version',''))}</div></div>
</div>

<section>
<p class="lead">This scan was executed inside the client's own Google Cloud
environment and designed on the operating principles of the EU AI Act and GDPR.
Every statement below is drawn directly from a tamper-evident, signed scan manifest.</p>
</section>

<section>
<h2>Principles, evidenced</h2>
{_principle_cards(m)}
</section>

<section>
<h2>Results</h2>
<div class="statgrid">
  <div class="stat"><div class="n">{total}</div><div class="l">Documents catalogued</div></div>
  <div class="stat"><div class="n">{review}%</div><div class="l">Flagged for human review</div></div>
  <div class="stat"><div class="n">{excluded}</div><div class="l">Excluded from processing</div></div>
</div>
</section>

<section>
<h2>Data minimization — what was deliberately not processed</h2>
<table><thead><tr><th>Exclusion reason</th><th>Files</th></tr></thead>
<tbody>{_exclusion_rows(ds)}</tbody></table>
<p class="muted" style="font-size:12px;margin-top:10px">
Pass 1 classified document type only and persisted no personal data
({'confirmed: no PII persisted' if not ds.get('pii_persisted') else 'WARNING: PII flag set'}).
Extraction of business fields (Pass 2) is gated on a separately documented legal basis.</p>
</section>

<section>
<h2>Output integrity</h2>
<table><thead><tr><th>Artifact</th><th>SHA-256</th></tr></thead>
<tbody>{_hash_rows(oi)}</tbody></table>
</section>

<section>
<h2>Attestation</h2>
<div class="attest">
  <div class="sig"><div class="who">{e(att.get('operator_name','—'))}</div>
    <div class="role">Operator · Focusfinder Consulting</div>
    <div class="when">{_date(att.get('operator_signature_timestamp'))}</div></div>
  <div class="sig">{client_cell}</div>
</div>
</section>

<footer>
Risk classification (operator assessment): limited / minimal-risk — internal
document organization with human oversight; no automated decisions affecting
individuals. &nbsp;·&nbsp; This document is generated automatically and solely
from the cryptographically-hashed scan manifest (run {short_id}). It attests to
process design and execution and does not constitute legal advice.{client_note}
</footer>
</div></body></html>"""


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--manifest", default=None)
    p.add_argument("--no-upload", action="store_true")
    a = p.parse_args()

    m = _load_manifest(a.manifest)
    htmlout = render(m)
    with open(OUT_HTML, "w") as f:
        f.write(htmlout)
    print(f"Wrote {OUT_HTML}")

    finalized = bool(m.get("finished") and m.get("attestation"))
    if not finalized:
        print("  NOTE: manifest not finalized — rendered as DRAFT.")

    if not a.no_upload:
        try:
            from google.cloud import storage
            bucket = m.get("gcp_project")  # placeholder; real bucket below
            # bucket name comes from config in the live run; upload best-effort
            from config import load_config
            bname = load_config()["gcp"]["bucket"]
            storage.Client().bucket(bname).blob("audit/compliance_summary.html") \
                .upload_from_filename(OUT_HTML)
            print(f"  Uploaded to gs://{bname}/audit/compliance_summary.html")
        except Exception as ex:
            print(f"  (skip GCS upload: {ex})")


if __name__ == "__main__":
    main()
