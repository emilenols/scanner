# Document Scanner — Walkthrough
**For Alex (Execution Operator) · Lease Estate · Companion to Addendum A v2.1**

This analyses your mirror folder, proposes how to organise it, and builds a
structured catalog of every document — by type, language, and confidence —
entirely inside **your own** Google environment. Nothing leaves your tenant.
This is the first step in turning an unstructured archive into an AI-ready,
queryable data foundation.

**Total time:** ~45 min of active work + a few hours of unattended batch wait.
**Skill level:** between low-code and developer. No prior Google Cloud experience needed.

| Convention | Meaning |
|---|---|
| DO THIS | the action to take |
| YOU SHOULD SEE | what a correct result looks like |
| IF WRONG | how to recover |

**The 20-minute rule:** if a step blocks you for more than 20 minutes, use the prompt in Part 10 or call Emile. Don't grind.

**Your checkpoints with Emile** (everything else is yours to run):
1. **Taxonomy** — the tool *proposes* it from your drive; you review/edit it. Loop Emile in if unsure (Part 5.3).
2. **Model** — if the model in your config isn't valid (Part 5.1).
3. **Gate B** — if the pilot review fails (Part 6).

---

## Part 0 — Prerequisites

**DO THIS:** Confirm each (write YES/NO):
- The OneDrive to Google Drive sync is live, and you can see the mirror folder with real files at drive.google.com
- You can sign in to console.cloud.google.com with a Google account
- You have a credit card for Google Cloud billing (charges only what's used — expected total: $2–40)
- You have the one-line bootstrap command from Emile (Part 3)

**IF a NO:** No sync -> finish the sync step first. No Google Cloud access -> this is the project's main risk; tell Emile.

---

## Part 1 — Open Cloud Shell

**DO THIS:**
1. Open https://console.cloud.google.com/
2. Top-right: click the `>_` icon (Activate Cloud Shell). First time -> **Continue** to authorize.

**YOU SHOULD SEE:** A terminal opens at the bottom of the browser, prompt ending in `:~$`.

---

## Part 2 — Build your config (answer a few questions — no file editing)

You don't edit any files here. A small helper asks you a handful of plain
questions and writes the config for you, with all the technical settings on safe
defaults. ~5 minutes.

**2.1 — Get the helper and run it:**
```
curl -O https://raw.githubusercontent.com/emilenols/scanner/main/init_config.py
python3 init_config.py
```

**2.2 — Answer the questions.** Where a default appears in `[brackets]`, just
press Enter to accept it. Have these ready:

| It asks | What to type |
|---|---|
| Your company's legal name | e.g. `Lease Estate NV` |
| A reference for this engagement | anything (a default is offered) |
| Who is running this scan | your name or team |
| A project ID | press Enter to accept the suggestion, or type your own |
| A storage bucket name | press Enter to accept the suggestion |
| The **exact** name of your mirror folder in Drive | copy it character-for-character from drive.google.com |
| One line describing your business | e.g. `Belgian commercial real estate leasing company` |
| Who signs off the document categories | a name + role (a business owner is ideal) |
| Who runs the pilot review | a name + role (defaults to you) |

**YOU SHOULD SEE:** `Wrote ~/client_config.yaml`, then a summary and the
service-account email you'll use later.

**What you are NOT asked** — and why that's good:
- **The document types.** You don't invent them. The Drive Analysis in Part 5.3
  reads your actual files and proposes the list for you to approve.
- **The technical settings** (region, model, confidence thresholds, the GDPR
  safety lock). The helper sets these to safe, tested defaults. You never touch
  them — and the GDPR lock that prevents any personal-data extraction is on by
  default.

**IF WRONG:** A value rejected (e.g. a project ID with capitals or spaces) → the
helper explains the rule and re-asks; just retype. Made a mistake after it
finished? Re-run `python3 init_config.py` and it offers to overwrite.

**(Optional, advanced) Prefer to edit the file directly?** You can instead
`curl -O .../client_config.example.yaml`, `cp` it to `~/client_config.yaml`, and
`cloudshell edit` it — but YAML indentation is easy to break, so the helper above
is the recommended path for everyone.

---

## Part 3 — Run the bootstrap

Reads your config, creates the cloud project / service account / storage, downloads the scanner, installs everything. ~3 minutes.

**DO THIS:** Paste the one line Emile gave you:
```
bash <(curl -s https://raw.githubusercontent.com/emilenols/scanner/main/setup.sh)
```

**YOU SHOULD SEE:** Progress, then a **"BOOTSTRAP COMPLETE — 3 human actions remain"** block.

**IF WRONG:** `~/client_config.yaml not found` -> redo Part 2. `'<FIELD>' could not be read` -> a formatting slip; reopen `cloudshell edit ~/client_config.yaml` and check that line's indentation. `quota exceeded` -> tell Emile.

---

## Part 4 — The 3 human actions (the bootstrap prints these)

**[1] Enable billing:** Open the billing link printed. Link a billing account (add a card if needed). Confirm billing **Active**.

**[2] Share the Drive folder:** drive.google.com -> right-click your mirror folder -> **Share**. Paste the **service account email** the bootstrap printed (ends `...iam.gserviceaccount.com`). Set **Viewer**. **Uncheck "Notify people."** Share.

**[3] Create the Gemini key:** https://aistudio.google.com/apikey -> **Create API key** -> select your project -> copy (starts `AIza...`). Then:
```
echo 'export GEMINI_API_KEY="AIza...PASTE_HERE..."' >> ~/.bashrc && source ~/.bashrc
```

---

## Part 5 — Analyse, organise, pilot

**DO THIS:** Start each session with:
```
cd ~/scanner && source venv/bin/activate
```

**5.1 — Confirm your model (first run):**
```
python list_models.py
```
Lists the model IDs in your project. **If `routing.model` isn't listed, stop**, edit `cloudshell edit ~/scanner/client_config.yaml`, set it to a listed `flash-lite` model, re-run. Unsure? Checkpoint with Emile.

**5.2 — Inventory the folder:**
```
python phase_a_scanner.py
```
> **Checkpoint — send to Emile:** `python checkpoint.py inventory` then send the file it writes. This is a safe, metadata-only summary (no file contents or names). It lets Emile confirm the corpus looks right before you spend time on the scan.
A progress bar, then file counts by type. **IF WRONG:** `Folder ... not found` -> redo the share (action [2]) or `source_folder` doesn't match Drive exactly. `Drive API has not been used` -> wait 1 min, retry.

**5.3 — Drive Analysis: discover the taxonomy (this is the key step):**
```
python discover_taxonomy.py
```
This reads a sample of your actual documents and proposes how to organise them.
It writes two files: a report and a plain editable list.

**DO THIS:**
1. Download **`drive_analysis.md`** (terminal **⋮ -> Download**) and open it. It shows the document types found (ranked, with confidence and estimated counts), which folders they live in, and a scan-quality note.
2. Open the plain list and edit it — no file format to worry about, just one type per line:
```
cloudshell edit ~/scanner/proposed_taxonomy.txt
```
Rename a type by retyping it, drop one by deleting its line, add one by adding a line. (A type you leave out gets filed into the nearest remaining bin — so add anything real the sample missed.) You don't need to add "Unknown" — it's added for you. Unsure where to draw the lines? This is checkpoint #1 with Emile. Save when done.
3. Apply your approved list to the config — one command, no YAML editing:
```
python apply_taxonomy.py
```
It writes your types into the config correctly and records your approval.

**This approved taxonomy is your Gate A.**

> **Checkpoint — send to Emile:** `python checkpoint.py discovery` then send the file. Emile will sanity-check the proposed categories with you before the pilot — this is checkpoint #1.

*(Advanced: you can instead edit `taxonomy.document_types` directly in `cloudshell edit ~/scanner/client_config.yaml`, keeping `"Unknown"` last — but the plain-list + apply path above avoids any YAML pitfalls.)*

**5.4 — Pilot (200 documents):**
```
python pilot_scanner.py
```
10–25 min; ends with a type summary and review rate. **IF WRONG:** lots of `Unknown` -> your taxonomy may have a gap; revisit 5.3 or raise with Emile.

> **Checkpoint — send to Emile:** `python checkpoint.py pilot` then send the file, *before* you do Gate B. Emile reviews the quality signals and tells you if anything needs adjusting.

---

## Part 6 — Gate B (your review — required)

**DO THIS:**
1. Download `pilot_catalog.csv` (⋮ -> Download).
2. Open in Excel/Sheets. Pick **20 rows at random.** For each, open the original in Drive and check `document_type` + `language`.
3. Record your verdict:
```
python gate_b.py --sample 20 --correct <N> --approver "Your Name" --role "Execution Operator"
```

**PASSES if** at least 18/20 correct **and** review rate < 20%. The script tells you.

**IF IT FAILS:** Don't proceed — checkpoint #3. Bring it to Emile; usually it's poor scans, fixed by a one-line model change.

---

## Part 7 — Full scan + catalog

**7.1 — Submit the batch** (server-side; you can close Cloud Shell after):
```
python pass1_scanner.py
```
**IF WRONG:** "Gate B not passed" -> do Part 6 first.

**7.2 — Check back later** (reopen Cloud Shell, then `cd ~/scanner && source venv/bin/activate`):
```
python check_batch.py
```
`JOB_STATE_RUNNING` -> later. `JOB_STATE_SUCCEEDED` -> results download automatically.

**7.3 — Assemble the catalog:**
```
python assemble_catalog.py
```
Writes `catalog_v1.{csv,jsonl,parquet}`, finalizes the manifest. Review rate should be < 20%.

**7.4 — Generate the attestation:**
```
python render_compliance_summary.py
```
Writes `compliance_summary.html` — interim, "awaiting client sign-off".

---

## Part 8 — Hand off + sign-off

**DO THIS:**
1. Download `catalog_v1.csv` and `compliance_summary.html` (⋮ -> Download).
2. Send both to the business owner who accepts the catalog; ask for a short review.
3. After they review, that approver (or you, once confirmed) runs:
```
python client_signoff.py --approver "<approver name>" --role "<role>" --confirm
```
Re-generates `compliance_summary.html` as the final **countersigned** version. Share that one.

---

## Part 9 — What you can hand the client

- **`drive_analysis.md`** — the plain-language "here's what's on the drive and how we'll organise it" report (from 5.3).
- **`catalog_v1.csv`** — the structured catalog of every document.
- **`compliance_summary.html`** — the countersigned attestation.

---

## Part 9b — Sending status to Emile (safe by design)

At each checkpoint above, one command writes a short report you send to Emile so
he can check progress and help improve things — without ever seeing your
documents. The reports contain **only aggregate numbers** (counts, categories,
confidence, error reasons): **no file contents, no file names, no folder names.**
Your documents never leave your environment.

```
python checkpoint.py doctor       # when something is stuck — environment snapshot
python checkpoint.py inventory    # after 5.2
python checkpoint.py discovery    # after 5.3
python checkpoint.py pilot        # after 5.4, before Gate B
python checkpoint.py catalog      # after 7.3
```

Each writes a `checkpoint_<step>.md` file (and prints it). Download it
(**⋮ -> Download**) and email it, or copy-paste the printed text. When you're
stuck, run `python checkpoint.py doctor` and send that **plus** the last ~15 lines
of any red error text.

## Part 10 — If something breaks

**Paste into Claude** with your error:
> I'm running a Python script in Google Cloud Shell for a document scanner.
> Error: [PASTE]. Setup: a service account is shared with the Drive folder as
> Viewer, the Drive API is enabled, and GOOGLE_APPLICATION_CREDENTIALS points to
> the SA key. Please diagnose, give the exact fix, and how to verify.

Common fixes:
- **Config value can't be read** -> `cloudshell edit ~/scanner/client_config.yaml`; check indentation.
- **Folder not found** -> redo the share (Part 4 [2]); confirm `source_folder` matches Drive.
- **403 / Drive API not used** -> just enabled; wait a minute, retry.
- **Model not found** -> `list_models.py`, fix `routing.model`, ask Emile.
- **API quota exceeded** -> wait 60s, retry.

If unresolved in ~20 minutes, escalate to Emile.

---

## Done when

- `catalog_v1.*` and the manifest exist in your project's storage bucket
- Review rate < 20%
- The countersigned `compliance_summary.html` is shared with the approver
- Cloud Shell can be closed — nothing keeps running, no ongoing cost beyond ~€0.50/month storage
