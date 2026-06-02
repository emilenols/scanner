#!/bin/bash
# =============================================================================
# Compliant Data Foundation — One-Paste Bootstrap (Cloud Shell)
# Companion to Addendum A v2.1 · Focusfinder Consulting
#
# GENERIC. All client values are read from ~/client_config.yaml (delivered by
# Focusfinder out-of-band and uploaded to Cloud Shell before running this).
# Nothing client-specific lives in this file or in the public repo.
#
# Run inside the CLIENT's Google Cloud Shell:
#   bash <(curl -s https://raw.githubusercontent.com/emilenols/scanner/main/setup.sh)
# =============================================================================
set -euo pipefail

SCANNER_REPO="https://github.com/emilenols/scanner.git"   # public; no secrets, no client data
CFG="$HOME/client_config.yaml"

# 0. Require the client config (uploaded by Alex before running) ------------- #
if [ ! -f "$CFG" ]; then
  echo "ERROR: ~/client_config.yaml not found."
  echo "Upload the client_config.yaml you received from Focusfinder to Cloud"
  echo "Shell home (vertical-dots menu -> Upload), then re-run this command."
  exit 1
fi

get_cfg(){ grep -E "^[[:space:]]*$1:" "$CFG" | head -1 \
  | sed -E "s/^[^:]*:[[:space:]]*//; s/[\"']//g; s/[[:space:]]*$//"; }

PROJECT_ID="$(get_cfg project_id)"
REGION="$(get_cfg region)"
BUCKET="$(get_cfg bucket)"
SA_NAME="$(get_cfg service_account)"
DRIVE_FOLDER="$(get_cfg source_folder)"

for v in PROJECT_ID REGION BUCKET SA_NAME DRIVE_FOLDER; do
  if [ -z "${!v}" ]; then
    echo "ERROR: '$v' could not be read from client_config.yaml — check the file."
    exit 1
  fi
done
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
echo "=== Bootstrap for ${PROJECT_ID} (region ${REGION}) ==="

# 1. Project ---------------------------------------------------------------- #
gcloud projects create "$PROJECT_ID" --name="$PROJECT_ID" 2>/dev/null || \
  echo "  project exists or already owned — continuing"
gcloud config set project "$PROJECT_ID" >/dev/null

# 2. APIs ------------------------------------------------------------------- #
echo "Enabling APIs..."
gcloud services enable \
  generativelanguage.googleapis.com \
  drive.googleapis.com \
  storage.googleapis.com \
  cloudshell.googleapis.com

# 3. Service account + role ------------------------------------------------- #
gcloud iam service-accounts create "$SA_NAME" \
  --description="Document intelligence scanner" \
  --display-name="Scanner SA" 2>/dev/null || echo "  SA exists — continuing"

# SA creation is eventually consistent — wait until it's visible before binding,
# otherwise the next call can fail with "does not exist".
echo "Waiting for the service account to be ready..."
for i in $(seq 1 12); do
  if gcloud iam service-accounts describe "$SA_EMAIL" >/dev/null 2>&1; then
    break
  fi
  sleep 5
done
if ! gcloud iam service-accounts describe "$SA_EMAIL" >/dev/null 2>&1; then
  echo "ERROR: service account ${SA_EMAIL} did not become available. Re-run this command."
  exit 1
fi

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/storage.objectAdmin" >/dev/null

# storage uploads also resolve the project for quota/billing, which needs
# serviceusage.services.use — not included in storage.objectAdmin.
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/serviceusage.serviceUsageConsumer" >/dev/null

# 4. SA key (stays in this tenant's Cloud Shell only) ----------------------- #
if [ ! -f "$HOME/scanner-sa-key.json" ]; then
  gcloud iam service-accounts keys create "$HOME/scanner-sa-key.json" \
    --iam-account="$SA_EMAIL"
fi
chmod 600 "$HOME/scanner-sa-key.json"

# 5. GCS bucket ------------------------------------------------------------- #
gcloud storage buckets create "gs://${BUCKET}" \
  --location="$REGION" --uniform-bucket-level-access \
  --public-access-prevention 2>/dev/null || echo "  bucket exists — continuing"

# 6. Scanner code + the client config --------------------------------------- #
if [ ! -d "$HOME/scanner/.git" ]; then
  git clone "$SCANNER_REPO" "$HOME/scanner"
else
  (cd "$HOME/scanner" && git pull --ff-only)
fi
cp "$CFG" "$HOME/scanner/client_config.yaml"   # the scripts read it from here
cd "$HOME/scanner"
python3 -m venv venv
source venv/bin/activate
pip install -q --upgrade pip
pip install -q google-genai google-api-python-client google-auth pydantic \
  pandas pyarrow tqdm tenacity google-cloud-storage pyyaml python-docx openpyxl

# 7. Environment ------------------------------------------------------------ #
grep -q GOOGLE_APPLICATION_CREDENTIALS ~/.bashrc || cat >> ~/.bashrc <<EOF
export GOOGLE_APPLICATION_CREDENTIALS="\$HOME/scanner-sa-key.json"
export BUCKET_NAME="${BUCKET}"
export PROJECT_ID="${PROJECT_ID}"
# GEMINI_API_KEY set by you below
EOF

# 8. Billing check (best effort) -------------------------------------------- #
BILLING=$(gcloud beta billing projects describe "$PROJECT_ID" \
  --format="value(billingEnabled)" 2>/dev/null || echo "unknown")

echo ""
echo "=================================================="
echo " BOOTSTRAP COMPLETE — 3 human actions remain"
echo "=================================================="
if [ "$BILLING" != "True" ]; then
  echo " [1] ENABLE BILLING (required — scan fails without it):"
  echo "     https://console.cloud.google.com/billing/linkedaccount?project=${PROJECT_ID}"
else
  echo " [1] Billing: ACTIVE"
fi
echo ""
echo " [2] SHARE the Drive folder '${DRIVE_FOLDER}' (Viewer) with:"
echo "       ${SA_EMAIL}"
echo "     (drive.google.com -> right-click folder -> Share -> uncheck Notify)"
echo ""
echo " [3] GEMINI API KEY: create at https://aistudio.google.com/apikey"
echo "     then run:"
echo "       echo 'export GEMINI_API_KEY=\"AIza...\"' >> ~/.bashrc && source ~/.bashrc"
echo ""
echo "Then run the scan, in order:"
echo "  cd ~/scanner && source venv/bin/activate"
echo "  python list_models.py            # (optional) confirm current model IDs"
echo "  python phase_a_scanner.py        # inventory"
echo "  python discover_taxonomy.py      # Drive Analysis -> read drive_analysis.md, edit taxonomy (Gate A)"
echo "  python pilot_scanner.py          # 200-doc pilot"
echo "  python gate_b.py --sample 20 --correct <N> --approver \"<name>\" --role \"<role>\""
echo "  python pass1_scanner.py          # submit full batch"
echo "  python check_batch.py            # poll (return in 1-24h)"
echo "  python assemble_catalog.py       # final catalog + manifest"
echo "  python render_compliance_summary.py   # board-ready attestation (HTML)"
echo "  # -> send catalog + interim attestation to the client approver"
echo "  python client_signoff.py --approver \"<name>\" --role \"<role>\" --confirm"
