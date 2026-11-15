#!/usr/bin/env python3
"""Conformance tests for node1-governance-kernel JSON schemas.

Validates that:
1. Each schema is valid JSON Schema draft 2020-12
2. Valid example documents pass validation
3. Invalid documents are correctly rejected
4. Required fields are enforced
"""
import json
import pytest
from pathlib import Path

try:
    from jsonschema import Draft202012Validator, ValidationError
except ImportError:
    pytest.skip("jsonschema not installed", allow_module_level=True)

SCHEMA_DIR = Path(__file__).resolve().parent.parent.parent / "schemas"

VALID_TASK_PACKET = {
    "packet_id": "PKT-REVIEW-20260101-AUTH",
    "version": "1.0",
    "title": "Review authentication module for security vulnerabilities",
    "scope": {
        "files": ["src/auth/login.py", "src/auth/session.py"],
        "description": "Security review of the authentication module",
        "lanes": ["security"]
    },
    "risk_class": "YELLOW",
    "risk_triggers": ["secret"],
    "acceptance_criteria": [
        "No P0 or P1 findings in review",
        "All secrets use vault, not env vars"
    ],
    "assigned_to": "reviewer-1",
    "review_required": True,
    "created_at": "2026-10-15T14:30:00Z"
}

VALID_RISK_BOUNDARY = {
    "boundary_id": "node1-default-safety",
    "version": "1.0",
    "categories": [
        {
            "name": "secret",
            "trigger_patterns": ["*.env", "**/secrets/**", "**/*key*", "**/*token*"],
            "action": "BLOCK",
            "exceptions": ["tests/fixtures/**"]
        },
        {
            "name": "delete",
            "trigger_patterns": ["rm -rf *", "DROP TABLE *", "DELETE FROM *"],
            "action": "REQUIRE_APPROVAL"
        }
    ],
    "enforcement_level": "BROKER_SOFT",
    "fallback_action": "BLOCK"
}

VALID_PLAN_BASELINE = {
    "plan_id": "PLAN-KERNEL-M3-001",
    "version": "1.0",
    "title": "M3 OSS Launch Plan Baseline",
    "steps": [
        {
            "step_number": 1,
            "description": "Create repo structure and LICENSE",
            "risk_class": "GREEN",
            "estimated_duration": "1h"
        },
        {
            "step_number": 2,
            "description": "Export clean code from M1+M2",
            "risk_class": "YELLOW",
            "estimated_duration": "3h",
            "dependencies": [1]
        }
    ],
    "content_sha256": "a" * 64,
    "approved_by": "project-lead",
    "approved_at": "2026-11-15T10:00:00Z"
}

VALID_EVIDENCE_MANIFEST = {
    "manifest_id": "EVM-20261015-001",
    "version": "1.0",
    "call_id": "broker-call-42",
    "agent_uid": 1001,
    "tool_name": "read_file",
    "input_sha256": "b" * 64,
    "output_sha256": "c" * 64,
    "governance_commitment": "governance-commitment-1",
    "admitted": True,
    "timestamp_start": "2026-10-15T14:30:00Z",
    "timestamp_end": "2026-10-15T14:30:01Z",
    "verdict": "PASS"
}

VALID_INDEPENDENCE_RECEIPT = {
    "receipt_id": "IR-20260101-REVIEW-R1",
    "version": "1.0",
    "artifact_sha256": "d" * 64,
    "artifact_path": "src/protocol/frames.py",
    "reviewer_id": "reviewer-session-abc123",
    "reviewer_vendor": "vendor-b",
    "author_vendor": "vendor-a",
    "independence_verdict": "VERIFIED",
    "review_verdict": "PASS",
    "findings": {
        "p0_count": 0,
        "p1_count": 0,
        "p2_count": 0,
        "details": []
    },
    "reviewed_at": "2026-10-15T16:00:00Z"
}

SCHEMAS = {
    "task_packet": (VALID_TASK_PACKET, "task_packet.schema.json"),
    "risk_boundary": (VALID_RISK_BOUNDARY, "risk_boundary.schema.json"),
    "plan_baseline": (VALID_PLAN_BASELINE, "plan_baseline.schema.json"),
    "evidence_manifest": (VALID_EVIDENCE_MANIFEST, "evidence_manifest.schema.json"),
    "independence_receipt": (VALID_INDEPENDENCE_RECEIPT, "independence_receipt.schema.json"),
}


def load_schema(name: str) -> dict:
    path = SCHEMA_DIR / name
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


class TestSchemaValidity:
    """Each schema file is valid JSON Schema draft 2020-12."""

    @pytest.mark.parametrize("schema_file", list(SCHEMA_DIR.glob("*.schema.json")))
    def test_schema_is_valid(self, schema_file):
        with open(schema_file, "r", encoding="utf-8") as f:
            schema = json.load(f)
        Draft202012Validator.check_schema(schema)


class TestValidDocuments:
    """Valid example documents pass validation."""

    @pytest.mark.parametrize("name,fixture", list(SCHEMAS.items()))
    def test_valid_document_passes(self, name, fixture):
        doc, schema_file = fixture
        schema = load_schema(schema_file)
        validator = Draft202012Validator(schema)
        validator.validate(doc)


class TestRequiredFields:
    """Missing required fields are rejected."""

    @pytest.mark.parametrize("name,fixture", list(SCHEMAS.items()))
    def test_empty_object_rejected(self, name, fixture):
        _, schema_file = fixture
        schema = load_schema(schema_file)
        validator = Draft202012Validator(schema)
        with pytest.raises(ValidationError):
            validator.validate({})

    def test_task_packet_missing_title(self):
        doc = {k: v for k, v in VALID_TASK_PACKET.items() if k != "title"}
        schema = load_schema("task_packet.schema.json")
        with pytest.raises(ValidationError, match="title"):
            Draft202012Validator(schema).validate(doc)

    def test_evidence_manifest_missing_verdict(self):
        doc = {k: v for k, v in VALID_EVIDENCE_MANIFEST.items() if k != "verdict"}
        schema = load_schema("evidence_manifest.schema.json")
        with pytest.raises(ValidationError, match="verdict"):
            Draft202012Validator(schema).validate(doc)

    def test_independence_receipt_missing_reviewer_vendor(self):
        doc = {k: v for k, v in VALID_INDEPENDENCE_RECEIPT.items() if k != "reviewer_vendor"}
        schema = load_schema("independence_receipt.schema.json")
        with pytest.raises(ValidationError, match="reviewer_vendor"):
            Draft202012Validator(schema).validate(doc)


class TestEnumConstraints:
    """Enum fields reject invalid values."""

    def test_task_packet_invalid_risk_class(self):
        doc = {**VALID_TASK_PACKET, "risk_class": "PURPLE"}
        schema = load_schema("task_packet.schema.json")
        with pytest.raises(ValidationError):
            Draft202012Validator(schema).validate(doc)

    def test_evidence_manifest_invalid_verdict(self):
        doc = {**VALID_EVIDENCE_MANIFEST, "verdict": "MAYBE"}
        schema = load_schema("evidence_manifest.schema.json")
        with pytest.raises(ValidationError):
            Draft202012Validator(schema).validate(doc)

    def test_independence_receipt_invalid_independence_verdict(self):
        doc = {**VALID_INDEPENDENCE_RECEIPT, "independence_verdict": "KINDA"}
        schema = load_schema("independence_receipt.schema.json")
        with pytest.raises(ValidationError):
            Draft202012Validator(schema).validate(doc)

    def test_risk_boundary_invalid_enforcement_level(self):
        doc = {**VALID_RISK_BOUNDARY, "enforcement_level": "WISH_REALLY_HARD"}
        schema = load_schema("risk_boundary.schema.json")
        with pytest.raises(ValidationError):
            Draft202012Validator(schema).validate(doc)


class TestAdditionalPropertiesRejected:
    """No extra fields allowed (strict schema)."""

    @pytest.mark.parametrize("name,fixture", list(SCHEMAS.items()))
    def test_extra_field_rejected(self, name, fixture):
        doc, schema_file = fixture
        doc_with_extra = {**doc, "unexpected_field": "should_fail"}
        schema = load_schema(schema_file)
        with pytest.raises(ValidationError):
            Draft202012Validator(schema).validate(doc_with_extra)


class TestPatternConstraints:
    """Pattern fields validate correctly."""

    def test_task_packet_id_pattern(self):
        doc = {**VALID_TASK_PACKET, "packet_id": "lowercase-bad"}
        schema = load_schema("task_packet.schema.json")
        with pytest.raises(ValidationError):
            Draft202012Validator(schema).validate(doc)

    def test_sha256_pattern(self):
        doc = {**VALID_EVIDENCE_MANIFEST, "input_sha256": "not-a-sha"}
        schema = load_schema("evidence_manifest.schema.json")
        with pytest.raises(ValidationError):
            Draft202012Validator(schema).validate(doc)
