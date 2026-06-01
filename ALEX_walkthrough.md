# Document Scanner — Walkthrough
**For Alex (Execution Operator) · Lease Estate · Companion to Addendum A v2.1**

This builds a structured catalog of every document in your mirror folder —
classified by type, language, and confidence — entirely inside **your own**
Google environment. Nothing leaves your tenant. You own the taxonomy and run
every step; Focusfinder provides the tooling and advises where noted.

**Total time:** ~40 min of active work + a few hours of unattended batch wait.
**Skill level:** between low-code and developer. No prior Google Cloud experience needed.

| Convention | Meaning |
|---|---|
| DO THIS | the action to take |
| YOU SHOULD SEE | what a correct result looks like |
| IF WRONG | how to recover |

**The 20-minute rule:** if a step blocks you for more than 20 minutes, use the
prompt in Part 9 or call Emile. Don't grind.

**Your three checkpoints with Emile** (everything else is yours to run):
1. **Taxonomy design** — shaping the document types before you start (Part 2).
2. **Model choice** — if the model in your config isn't valid (Part 5.1).
3. **Gate B** — if the pilot review fails (Part 6).

---

## Part 0 — Prerequisites

**DO THIS:** Confirm each (write YES/NO):
- The OneDrive to Google Drive sync is live, and you can see the mirror folder with real files at drive.google.com
- You can sign in to console.cloud.google.com with a Google account
- You have a credit card for Google Cloud billing (it charges only what's used — expected total: $2–40)
- You have the one-line bootstrap command from Emile (Part 3)

**IF a NO:** No sync -> finish the sync step first. No Google Cloud access -> this is the project's main risk; tell Emile.

---

## Part 1 — Open Cloud Shell

**DO THIS:**
1. Open https://console.cloud.google.com/
2. Top-right: click the `>_` icon (Activate Cloud Shell). First time -> **Continue** to authorize.

**YOU SHOULD SEE:** A terminal opens at the bottom of the browser, prompt ending in `:~$`.

---

## Part 2 — Build your config

This file tells the scanner what your documents are and where they live. **You
author it** — the taxonomy is your call. It takes ~15 minutes.

**2.1 — Get the template:**

**DO THIS:** In Cloud Shell, paste:
```
curl -O https://raw.githubusercontent.com/emilenols/scanner/main/client_config.example.yaml
cp client_config.example.yaml ~/client_config.yaml
```

**2.2 — Open it in the editor:**

**DO THIS:**
```
cloudshell edit ~/client_config.yaml
```
The Cloud Shell web editor opens with the file. (YAML is indentation-sensitive: keep the structure of the template, only change the values after each `:`.)

**2.3 — Fill it.** Here's who decides what:

| Field | What to put | Who decides |
|---|---|---|
| `client`, `engagement_ref` | Lease Estate's name; any reference you like | **You** |
| `operator` | Who is running this scan (you / your team) | **You** |
| `gcp.project_id` | A new project ID, lowercase-with-hyphens (e.g. `lease-estate-data-lake`) | **You** |
| `gcp.region` | `europe-west1` | Leave default (keep EU for GDPR) |
| `gcp.bucket` | A **globally-unique** bucket name | **You** (add a suffix if taken) |
| `gcp.service_account` | `scanner-sa` | Leave default |
| `drive.source_folder` | The **exact** name of your mirror folder in Drive | **You** — must match character-for-character |
| `taxonomy.system_context` | One line describing your business | **You** |
| `taxonomy.document_types` | Your real document categories. Keep `"Unknown"` **last** | **You — the core of your job** |
| `taxonomy.languages` | `["nl","fr","en","mixed","unknown"]` | Leave default |
| `routing.model` | `gemini-2.5-flash-lite` | **Advisory** — confirm in Part 5.1; ask Emile if unsure |
| `routing.accept_threshold` / `review_threshold` | `0.85` / `0.70` | **Leave default** — changing these is a methodology call; raise with Emile |
| `routing.fallback_model` | `gemini-2.5-pro` | Leave default |
| `gdpr.pass1_legal_basis` | (leave the template text) | Leave default |
| `gdpr.pass2_legal_basis_ref` | `null` | **LEAVE NULL — do not touch.** This blocks any personal-data extraction until a legal basis is signed off. |
| `gates.gate_a_approver` | Who signs off the taxonomy (e.g. a business owner like Lloyd) | **You** |
| `gates.gate_b_approver` | Who runs the pilot review (you, or a colleague) | **You** |

> **The three fields where a wrong value bites:** `routing.model` (model IDs
> change over time — Part 5.1 verifies it), the `routing` thresholds (leave the
> defaults), and `gdpr.pass2_legal_basis_ref` (must stay `null`). Everything
> else is safe to set freely.

**2.4 — Designing the taxonomy (the part worth getting right):**
Open your mirror folder and look at what's actually there. Aim for **8–12
document types** that match how the business already talks about these files.
Always keep `"Unknown"` as the last entry — it's the safety net for anything the
scanner isn't sure about. If you're unsure where to draw the lines, this is
checkpoint #1 with Emile.

**DO THIS:** Save and close the editor (top-right X, or `Ctrl+S`).

---

## Part 3 — Run the bootstrap

This reads your config and creates the cloud project, service account, storage,
and installs the scanner. ~3 minutes.

**DO THIS:** Paste the one line Emile gave you:
```
bash <(curl -s https://raw.githubusercontent.com/emilenols/scanner/main/setup.sh)
```

**YOU SHOULD SEE:** Progress messages, then a **"BOOTSTRAP COMPLETE — 3 human actions remain"** block.

**IF WRONG:** `~/client_config.yaml not found` -> redo Part 2 (the file must be in your home folder). `'<FIELD>' could not be read from client_config.yaml` -> a formatting slip in Part 2; reopen `cloudshell edit ~/client_config.yaml` and check that line keeps the template's indentation. `quota exceeded` on project creation -> tell Emile.

---

## Part 4 — The 3 human actions (the bootstrap prints these)

These three need you, a logged-in human — they can't be scripted.

**[1] Enable billing:** Open the billing link the bootstrap printed. Link a billing account (add a card if needed). Confirm the project shows billing **Active**.

**[2] Share the Drive folder:** At drive.google.com, right-click your mirror folder -> **Share**. Paste the **service account email** the bootstrap printed (ends `...iam.gserviceaccount.com`). Set **Viewer**. **Uncheck "Notify people."** Share.

**[3] Create the Gemini key:** Open https://aistudio.google.com/apikey -> **Create API key** -> select your project -> copy it (starts `AIza...`). Then in Cloud Shell:
```
echo 'export GEMINI_API_KEY="AIza...PASTE_HERE..."' >> ~/.bashrc && source ~/.bashrc
```

---

## Part 5 — Run the scan, in order

**DO THIS:** Start each session with:
```
cd ~/scanner && source venv/bin/activate
```

**5.1 — Confirm your model (do this for the first run):**
```
python list_models.py
```
Lists the model IDs available in your project. **If the `routing.model` from your config isn't in the list, stop.** Edit `cloudshell edit ~/scanner/client_config.yaml`, set `routing.model` to a listed `flash-lite` model, and re-run. Unsure which? Checkpoint #2 — ask Emile.

**5.2 — Inventory the folder:**
```
python phase_a_scanner.py
```
A progress bar, then a summary of file counts by type. **IF WRONG:** `Folder ... not found` -> redo the folder share (action [2]), or your `source_folder` name doesn't match Drive exactly. `Drive API has not been used` -> wait 1 min, retry.

**5.3 — Pilot (200 documents):**
```
python pilot_scanner.py
```
Takes 10–25 min; ends with a document-type summary and a review rate. **IF WRONG:** Everything comes back `Unknown` -> your `system_context` or taxonomy may need tightening; refine in the config and re-run, or raise with Emile.

---

## Part 6 — Gate B (your review — required)

**DO THIS:**
1. The pilot wrote `pilot_catalog.csv`. Download it (terminal **⋮ -> Download**).
2. Open in Excel/Sheets. Pick **20 rows at random.** For each, open the original file in Drive and check whether `document_type` and `language` are right.
3. Record your verdict (this writes it into the audit record):
```
python gate_b.py --sample 20 --correct <N> --approver "Your Name" --role "Execution Operator"
```

**Gate B PASSES if** at least 18 of 20 are correct **and** the review rate is < 20%. The script tells you which.

**IF IT FAILS:** Don't proceed — this is checkpoint #3. Bring it to Emile. Usually it means many scanned/legacy PDFs, and the fix is a one-line model change in your config.

---

## Part 7 — Full scan + catalog

**7.1 — Submit the batch** (runs on Google's servers; you can close Cloud Shell after):
```
python pass1_scanner.py
```
Builds requests, prints "Submitted batch job", tells you to return in 1–24h. **IF WRONG:** "Gate B not passed" -> do Part 6 first.

**7.2 — Check back later** (reopen Cloud Shell, then `cd ~/scanner && source venv/bin/activate`):
```
python check_batch.py
```
`JOB_STATE_RUNNING` -> check again later. `JOB_STATE_SUCCEEDED` -> results download automatically.

**7.3 — Assemble the catalog:**
```
python assemble_catalog.py
```
Writes `catalog_v1.{csv,jsonl,parquet}`, finalizes the manifest, prints a summary. Review rate should be < 20%.

**7.4 — Generate the attestation:**
```
python render_compliance_summary.py
```
Writes `compliance_summary.html` — an interim attestation marked "awaiting client sign-off".

---

## Part 8 — Hand off + sign-off

**DO THIS:**
1. Download `catalog_v1.csv` and `compliance_summary.html` (⋮ -> Download).
2. Send both to the business owner who accepts the catalog; ask for a short review.
3. After they've reviewed it, that approver (or you, once they confirm) runs:
```
python client_signoff.py --approver "<approver name>" --role "<role>" --confirm
```
Records the sign-off and re-generates `compliance_summary.html` as the final **countersigned** version. Download and share that one.

---

## Part 9 — If something breaks

**Paste into Claude** with your error:
> I'm running a Python script in Google Cloud Shell for a document scanner.
> Error: [PASTE]. Setup: a service account is shared with the Drive folder as
> Viewer, the Drive API is enabled, and GOOGLE_APPLICATION_CREDENTIALS points to
> the SA key. Please diagnose, give the exact fix, and how to verify.

Common fixes:
- **Config value can't be read** -> reopen `cloudshell edit ~/scanner/client_config.yaml`; check indentation matches the template.
- **Folder not found** -> redo the folder share (Part 4 action [2]); confirm `source_folder` matches Drive exactly.
- **403 / Drive API not used** -> just enabled; wait a minute, retry.
- **Model not found** -> run `list_models.py`, fix `routing.model`, ask Emile if unsure.
- **API quota exceeded** (pilot) -> wait 60s, retry.

If a step isn't resolved in ~20 minutes, escalate to Emile.

---

## Done when

- `catalog_v1.*` and the manifest exist in your project's storage bucket
- Review rate < 20%
- The countersigned `compliance_summary.html` is shared with the approver
- Cloud Shell can be closed — nothing keeps running, no ongoing cost beyond ~€0.50/month storage
