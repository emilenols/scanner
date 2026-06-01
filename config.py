"""
config.py — per-client configuration boundary.

A new client = a new client_config.yaml. No code edits.
  * assert_pass2_allowed() is a HARD code interlock on the GDPR gate.
  * build_pass1_model() builds Gemini's response schema from the YAML taxonomy.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Literal, Optional, Type

import yaml
from pydantic import BaseModel, Field, create_model

DEFAULT_CONFIG_PATH = "client_config.yaml"


def load_config(path: str = DEFAULT_CONFIG_PATH) -> dict:
    with open(path) as fh:
        cfg = yaml.safe_load(fh)
    _validate(cfg)
    return cfg


def _validate(cfg: dict) -> None:
    required = ["client", "engagement_ref", "gcp", "drive", "taxonomy",
                "routing", "gdpr", "gates"]
    missing = [k for k in required if k not in cfg]
    if missing:
        raise ValueError(f"client_config.yaml missing keys: {missing}")
    if not cfg["taxonomy"].get("document_types"):
        raise ValueError("taxonomy.document_types is empty")
    if "Unknown" not in cfg["taxonomy"]["document_types"]:
        raise ValueError("taxonomy.document_types must include 'Unknown'")


def assert_pass2_allowed(cfg: dict) -> None:
    if not cfg.get("gdpr", {}).get("pass2_legal_basis_ref"):
        raise RuntimeError(
            "Pass 2 is BLOCKED: gdpr.pass2_legal_basis_ref is not set. "
            "Document the legal basis (signed off in P0) before extracting "
            "business fields. Hard compliance gate.")


def _enum_key(name: str) -> str:
    return re.sub(r"[^0-9a-zA-Z]+", "_", name).strip("_").upper() or "UNNAMED"


def build_document_type_enum(cfg: dict) -> Type[Enum]:
    members = {_enum_key(n): n for n in cfg["taxonomy"]["document_types"]}
    return Enum("DocumentType", members, type=str)


def build_pass1_model(cfg: dict) -> Type[BaseModel]:
    DocType = build_document_type_enum(cfg)
    langs = tuple(cfg["taxonomy"].get("languages",
                  ["nl", "fr", "en", "mixed", "unknown"]))
    return create_model(
        "Pass1Classification",
        document_type=(DocType, ...),
        sub_type=(Optional[str], Field(None, description="Finer-grained class")),
        language=(Literal[langs], ...),  # type: ignore[valid-type]
        confidence=(float, Field(ge=0.0, le=1.0)),
        reasoning=(str, Field(description="One-sentence explanation")),
    )


def system_instruction(cfg: dict) -> str:
    tax = cfg["taxonomy"]
    types_str = "\n  - ".join(tax["document_types"])
    return (
        f"You are classifying documents for a {tax['system_context']}.\n"
        f"Classify each document into exactly one of these types:\n"
        f"  - {types_str}\n"
        "Identify the language (one of the configured codes).\n"
        "Return a confidence score between 0 and 1 reflecting your certainty.\n"
        "Provide a one-sentence reasoning.\n"
        "DO NOT extract personal data or business details — classify the type only.")


def routing(cfg: dict) -> dict:
    return cfg["routing"]


def service_account_email(cfg: dict) -> str:
    g = cfg["gcp"]
    return f"{g['service_account']}@{g['project_id']}.iam.gserviceaccount.com"


def verify_model(client, model_id: str) -> None:
    """Preflight: confirm routing.model resolves in this project BEFORE the run.

    A stale/wrong model string is not transient — retrying it is pointless.
    This fails fast with the exact fix. If listing itself fails (SDK shape,
    permissions), it degrades to a warning rather than false-blocking the run;
    the live call will then surface the error.
    """
    try:
        available = [m.name for m in client.models.list()]
    except Exception as e:  # don't block on listing problems
        print(f"  Could not pre-verify model ({e}). Continuing; if "
              f"classification fails, run `python list_models.py` and check "
              f"routing.model in client_config.yaml.")
        return
    norm = {n.split("/")[-1] for n in available}
    if model_id.split("/")[-1] not in norm:
        tier = sorted(n.split("/")[-1] for n in available
                      if "flash-lite" in n or "pro" in n)
        print(f"\n  Configured model not available: routing.model = '{model_id}'")
        print("  Classification-tier models available in this project:")
        for n in tier:
            print(f"    - {n}")
        raise SystemExit(
            "Fix routing.model in client_config.yaml, then re-run "
            "(avoid '*-latest'/experimental IDs in production).")
