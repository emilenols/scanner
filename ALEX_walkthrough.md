# Document Scanner — Walkthrough
**For Alex (Implementation Lead) · Focusfinder Consulting · Addendum A v2.1**

This builds a structured catalog of every document in your mirror folder, all
inside your own Google environment. Nothing leaves your tenant.

**Total time:** ~30 min active work + a few hours of unattended batch wait.
**Skill level:** between low-code and developer. No prior Google Cloud experience needed.

**Conventions:**
✅ **DO THIS** — the action &nbsp; 👁 **YOU SHOULD SEE** — what to expect &nbsp; ⚠ **IF WRONG** — what to do

**The 20-minute rule:** if any step takes more than 20 minutes, use the prompt in
Part 9 or contact Emile. Don't grind.

---

## Part 0 — Prerequisites

✅ **DO THIS:** Confirm each is true (write YES/NO):
- The OneDrive → Google Drive sync is live and you can see the mirror folder with real files at drive.google.com
- You can sign in to console.cloud.google.com with a Google account
- You have a credit card for Google Cloud billing (it charges only what's used — expected total: $2–40)
- You received a file called **`client_config.yaml`** from Focusfinder

⚠ **IF a NO:** No sync → finish the sync step first. No `client_config.yaml` → ask Emile; you can't start without it.

---

## Part 1 — Open Cloud Shell

✅ **DO THIS:**
1. Open https://console.cloud.google.com/
2. Top-right: click the **`>_`** icon (Activate Cloud Shell). First time → click **Continue** to authorize.

👁 **YOU SHOULD SEE:** A terminal opens at the bottom of the browser with a prompt ending in `:~$`.

---

## Part 2 — Upload your config file

✅ **DO THIS:**
1. In Cloud Shell, top-right of the terminal: click the **⋮** (three dots) → **Upload**.
2. Select the `client_config.yaml` Focusfinder sent you. It lands in your home folder.

👁 **YOU SHOULD SEE:** `ls client_config.yaml` lists the file.

⚠ **IF WRONG:** If upload doesn't appear, run `ls ~` to confirm. It must be in the home directory (`~`), not a subfolder.

---

## Part 3 — Run the one-paste bootstrap

This creates the cloud project, service account, and storage, downloads the
scanner, and installs everything — from your config file. ~3 minutes.

✅ **DO THIS:** Paste this one line (Emile will give you the exact URL):

```
bash <(curl -s https://raw.githubusercontent.com/<ORG>/scanner/main/setup.sh)
```

👁 **YOU SHOULD SEE:** Progress messages, then a **"BOOTSTRAP COMPLETE — 3 human
actions remain"** block listing exactly what to do next.

⚠ **IF WRONG:** `~/client_config.yaml not found` → redo Part 2. `quota exceeded`
on project creation → tell Emile (this is the admin-access risk).

---

## Part 4 — The 3 human actions (the bootstrap prints these)

These three can't be automated — they need you, a logged-in human.

✅ **[1] Enable billing:** Open the billing link the bootstrap printed. Link a
billing account (add a card if none exists). Confirm the project shows billing **Active**.

✅ **[2] Share the Drive folder:** At drive.google.com, right-click your mirror
folder → **Share**. Paste the **service account email** the bootstrap printed
(ends in `...iam.gserviceaccount.com`). Set to **Viewer**. **Uncheck "Notify people"**. Share.

✅ **[3] Create the Gemini key:** Open https://aistudio.google.com/apikey →
**Create API key** → select your project → copy it (starts `AIza...`). Then in Cloud Shell:

```
echo 'export GEMINI_API_KEY="AIza...PASTE_HERE..."' >> ~/.bashrc && source ~/.bashrc
```

---

## Part 5 — Run the scan, in order

✅ **DO THIS:** Start each session with:
```
cd ~/scanner && source venv/bin/activate
```

Then run these one at a time:

**5.1 (optional) Confirm the model:**
```
python list_models.py
```
👁 Lists available model IDs. ⚠ If the model in your config isn't listed, **stop and tell Emile** — don't guess.

**5.2 Inventory the folder:**
```
python phase_a_scanner.py
```
👁 A progress bar, then a summary of file counts by type. ⚠ `Folder ... not found` → redo the folder share (action [2]). `Drive API has not been used` → wait 1 min and retry (the API was just enabled).

**5.3 Pilot (200 documents):**
```
python pilot_scanner.py
```
👁 Takes 10–25 min; ends with a document-type summary and a review rate. ⚠ Everything comes back `Unknown` → tell Emile (the prompt needs calibration).

---

## Part 6 — Gate B (your review — required)

✅ **DO THIS:**
1. Convert + download the pilot results: the pilot already wrote `pilot_catalog.csv`. Download it via the **⋮ → Download** menu.
2. Open it in Excel/Sheets. Pick **20 rows at random**. For each, open the original file in Drive and check whether `document_type` and `language` are right.
3. Record your verdict (this writes it into the audit record):
```
python gate_b.py --sample 20 --correct <N> --approver "Your Name" --role "Implementation Lead"
```

👁 **Gate B PASSES if** ≥ 18 of 20 are correct **and** the review rate is < 20%. The script tells you which.

⚠ **IF IT FAILS:** Don't proceed. Bring it to Emile — usually it means many scanned/legacy PDFs, and the fix is a model change he'll make in the config.

---

## Part 7 — Full scan + catalog

**7.1 Submit the batch** (runs on Google's servers; you can close Cloud Shell after):
```
python pass1_scanner.py
```
👁 Builds requests, prints "Submitted batch job", tells you to return in 1–24h. ⚠ "Gate B not passed" → do Part 6 first.

**7.2 Check back later** (re-open Cloud Shell, `cd ~/scanner && source venv/bin/activate`):
```
python check_batch.py
```
👁 `JOB_STATE_RUNNING` → check again later. `JOB_STATE_SUCCEEDED` → results downloaded automatically.

**7.3 Assemble the catalog:**
```
python assemble_catalog.py
```
👁 Writes `catalog_v1.{csv,jsonl,parquet}`, finalizes the manifest, prints a summary. Review rate should be < 20%.

**7.4 Generate the attestation:**
```
python render_compliance_summary.py
```
👁 Writes `compliance_summary.html` — an interim attestation marked "awaiting client sign-off".

---

## Part 8 — Hand off + client sign-off

✅ **DO THIS:**
1. Download `catalog_v1.csv` and `compliance_summary.html` (⋮ → Download).
2. Send both to the client approver (e.g. Lloyd); ask for a 1-hour review.
3. After they've reviewed it, the approver (or you, once they confirm) runs:
```
python client_signoff.py --approver "Lloyd <surname>" --role "<role>" --confirm
```
👁 Records the sign-off and re-generates `compliance_summary.html` — now the
final **countersigned** version. Download and share that one.

---

## Part 9 — If something breaks

✅ **Paste this into Claude** with your error:
> I'm running a Python script in Google Cloud Shell for a document scanner.
> Error: [PASTE]. Setup: service account shared with the Drive folder as Viewer,
> Drive API enabled, GOOGLE_APPLICATION_CREDENTIALS set to the SA key. Please
> diagnose, give the exact fix, and how to verify.

Common fixes:
- **Folder not found** → redo the folder share (Part 4 action [2]).
- **403 / Drive API not used** → it was just enabled; wait a minute, retry.
- **Model not found** → run `list_models.py`, then tell Emile.
- **API quota exceeded** (pilot) → wait 60s, retry.

If a step isn't resolved in ~20 minutes, escalate to Emile.

---

## Done when

- `catalog_v1.*` and the manifest exist in your project's storage bucket
- Review rate < 20%
- The countersigned `compliance_summary.html` is shared with the approver
- Cloud Shell can be closed — nothing keeps running, no ongoing cost beyond ~€0.50/month storage
