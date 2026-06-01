"""
manifest.py — Compliant Data Foundation scan manifest.

The audit trail IS the product. Built in Phase 0, before orchestration.

Properties enforced here:
  * Every mutation autosaves -> a crash leaves a VALID PARTIAL manifest.
  * Agent/human actions are logged honestly (actor field). No disguised automation.
  * The manifest RESUMES across Cloud Shell sessions (run_id.txt), so the same
    run survives the multi-hour Batch API wait.
  * finalize() hashes each catalog file and refuses to complete a run that is
    missing required evidence (data scope, a human gate, a processing record).
"""

from __future__ import annotations

import hashlib
import os
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field

RUN_ID_FILE = os.path.expanduser("~/scanner/run_id.txt")


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# Schema (frozen in Phase 0)
# --------------------------------------------------------------------------- #
class GateStatus(str, Enum):
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED_NOT_REACHED = "skipped_not_reached"


class HumanGate(BaseModel):
    gate: Literal["A_taxonomy_signoff", "B_pilot_review"]
    status: GateStatus
    approver_name: str
    approver_role: str
    timestamp: Optional[datetime] = None
    sample_size: Optional[int] = None
    sample_correct: Optional[int] = None
    review_rate_pct: Optional[float] = None
    notes: str = ""


class CommandRecord(BaseModel):
    timestamp: datetime
    actor: Literal["agent", "human"]
    action: str
    target: str
    result: Literal["success", "failure", "skipped_idempotent"]
    stderr_excerpt: Optional[str] = None


class DataScope(BaseModel):
    source_folder: str
    files_discovered: int
    files_in_scope: int
    files_excluded: int
    exclusion_reasons: dict = Field(default_factory=dict)
    pii_persisted: bool = False
    pass_scope: Literal["pass1_type_only", "pass2_fields"] = "pass1_type_only"


class ProcessingRecord(BaseModel):
    pass_name: Literal["pass1", "pass2"]
    model: str
    confidence_threshold_accept: float
    confidence_threshold_review: float
    confidence_threshold_fallback: float
    fallback_model: str
    counts_accepted: int = 0
    counts_review_queue: int = 0
    counts_fallback_invoked: int = 0
    review_rate_pct: float = 0.0


class AIActPrinciples(BaseModel):
    human_oversight: str = (
        "Gate A (taxonomy) and Gate B (pilot, 20-doc human review) before full run"
    )
    data_minimization: str = (
        "Two-pass: Pass 1 classifies type only and persists no PII; "
        "Pass 2 runs only against a documented legal basis"
    )
    transparency: str = (
        "Each classification carries a model-generated reasoning field and confidence score"
    )
    logging: str = "This manifest records every action, timestamp, and human gate"
    risk_classification: str = (
        "Limited/minimal-risk: internal document organization, "
        "no automated decisions affecting persons"
    )


class OutputIntegrity(BaseModel):
    catalog_files: dict = Field(default_factory=dict)
    total_rows: int = 0
    review_rate_pct: float = 0.0


class Attestation(BaseModel):
    operator_name: str
    operator_signature_timestamp: datetime
    client_approver_name: Optional[str] = None
    client_signature_timestamp: Optional[datetime] = None


class ScanManifest(BaseModel):
    schema_version: str = "manifest-v1.0"
    run_id: str
    client: str
    engagement_ref: str
    scanner_version: str = "Addendum A v2.1"
    started: datetime
    finished: Optional[datetime] = None
    gcp_project: str
    gcp_region: str
    service_account: str
    data_scope: Optional[DataScope] = None
    human_gates: list[HumanGate] = Field(default_factory=list)
    commands: list[CommandRecord] = Field(default_factory=list)
    processing: list[ProcessingRecord] = Field(default_factory=list)
    ai_act_principles: AIActPrinciples = Field(default_factory=AIActPrinciples)
    output_integrity: Optional[OutputIntegrity] = None
    attestation: Optional[Attestation] = None


# --------------------------------------------------------------------------- #
# Runtime wrapper
# --------------------------------------------------------------------------- #
def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class Manifest:
    def __init__(self, model: ScanManifest, local_path: str, save: bool = True):
        self.m = model
        self.local_path = local_path
        Path(local_path).parent.mkdir(parents=True, exist_ok=True)
        if save:
            self._save()

    # ---- construction / resume -------------------------------------------- #
    @classmethod
    def start_from_config(cls, cfg: dict, run_id: Optional[str] = None,
                          audit_dir: Optional[str] = None) -> "Manifest":
        run_id = run_id or str(uuid.uuid4())
        gcp = cfg["gcp"]
        sa = f"{gcp['service_account']}@{gcp['project_id']}.iam.gserviceaccount.com"
        model = ScanManifest(
            run_id=run_id, client=cfg["client"],
            engagement_ref=cfg["engagement_ref"], started=_now(),
            gcp_project=gcp["project_id"], gcp_region=gcp["region"],
            service_account=sa,
        )
        audit_dir = audit_dir or os.path.expanduser("~/scanner/audit")
        path = os.path.join(audit_dir, f"scan_manifest_{run_id}.json")
        return cls(model, path)

    @classmethod
    def load(cls, local_path: str) -> "Manifest":
        with open(local_path) as fh:
            model = ScanManifest.model_validate_json(fh.read())
        return cls(model, local_path, save=False)

    @classmethod
    def resume_or_start(cls, cfg: dict, audit_dir: Optional[str] = None) -> "Manifest":
        """Every script calls this. First run starts a manifest and pins the
        run_id; later sessions resume the same one."""
        audit_dir = audit_dir or os.path.expanduser("~/scanner/audit")
        if os.path.exists(RUN_ID_FILE):
            run_id = open(RUN_ID_FILE).read().strip()
            path = os.path.join(audit_dir, f"scan_manifest_{run_id}.json")
            if os.path.exists(path):
                return cls.load(path)
        m = cls.start_from_config(cfg, audit_dir=audit_dir)
        Path(RUN_ID_FILE).parent.mkdir(parents=True, exist_ok=True)
        with open(RUN_ID_FILE, "w") as fh:
            fh.write(m.m.run_id)
        return m

    # ---- mutations -------------------------------------------------------- #
    def log_command(self, actor, action, target, result, stderr_excerpt=None):
        self.m.commands.append(CommandRecord(
            timestamp=_now(), actor=actor, action=action, target=target,
            result=result, stderr_excerpt=stderr_excerpt))
        self._save()

    def record_gate(self, gate, status, approver_name, approver_role,
                    sample_size=None, sample_correct=None,
                    review_rate_pct=None, notes=""):
        self.m.human_gates.append(HumanGate(
            gate=gate, status=GateStatus(status), approver_name=approver_name,
            approver_role=approver_role, timestamp=_now(),
            sample_size=sample_size, sample_correct=sample_correct,
            review_rate_pct=review_rate_pct, notes=notes))
        self._save()

    def set_data_scope(self, source_folder, files_discovered, files_in_scope,
                       exclusion_reasons, pass_scope="pass1_type_only",
                       pii_persisted=False):
        self.m.data_scope = DataScope(
            source_folder=source_folder, files_discovered=files_discovered,
            files_in_scope=files_in_scope,
            files_excluded=files_discovered - files_in_scope,
            exclusion_reasons=exclusion_reasons, pass_scope=pass_scope,
            pii_persisted=pii_persisted)
        self._save()

    def add_processing(self, **kwargs):
        self.m.processing.append(ProcessingRecord(**kwargs))
        self._save()

    # ---- finalization ----------------------------------------------------- #
    def finalize(self, catalog_files: dict, operator_name: str,
                 total_rows: int, review_rate_pct: float,
                 client_approver_name: Optional[str] = None):
        missing = []
        if self.m.data_scope is None:
            missing.append("data_scope")
        if not self.m.human_gates:
            missing.append("human_gates (at least Gate B)")
        if not self.m.processing:
            missing.append("processing record")
        if missing:
            raise RuntimeError("Cannot finalize — missing: " + ", ".join(missing))
        self.m.output_integrity = OutputIntegrity(
            catalog_files={n: _sha256(p) for n, p in catalog_files.items()},
            total_rows=total_rows, review_rate_pct=review_rate_pct)
        self.m.attestation = Attestation(
            operator_name=operator_name, operator_signature_timestamp=_now(),
            client_approver_name=client_approver_name)
        self.m.finished = _now()
        self._save()

    def attest_client(self, client_approver_name: str):
        """Record a REAL client sign-off action — name + timestamp. Refuses
        until operator finalize has produced the catalog being signed off on.
        This is what makes the client attestation an action, not a config echo."""
        if self.m.attestation is None:
            raise RuntimeError(
                "Operator attestation missing — run assemble_catalog.py before "
                "client sign-off.")
        self.m.attestation.client_approver_name = client_approver_name
        self.m.attestation.client_signature_timestamp = _now()
        self._save()

    # ---- persistence ------------------------------------------------------ #
    def _save(self):
        with open(self.local_path, "w") as fh:
            fh.write(self.m.model_dump_json(indent=2))

    def upload_gcs(self, bucket_name, blob_path="audit/scan_manifest.json"):
        from google.cloud import storage
        storage.Client().bucket(bucket_name).blob(blob_path) \
            .upload_from_filename(self.local_path)
        return f"gs://{bucket_name}/{blob_path}"
