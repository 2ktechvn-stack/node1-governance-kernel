#!/usr/bin/env python3
"""Validate JSON documents against node1-governance-kernel schemas.

Usage:
    python -m node1_governance_kernel.validator schemas/task_packet.schema.json my_packet.json
    python -m node1_governance_kernel.validator --all-schemas data/
"""
import argparse
import json
import sys
from pathlib import Path

try:
    import jsonschema
    from jsonschema import Draft202012Validator
except ImportError:
    print("ERROR: jsonschema is required. Install with: pip install jsonschema", file=sys.stderr)
    sys.exit(1)


def load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_document(schema_path: str, document_path: str) -> list:
    """Validate a JSON document against a schema. Returns list of error messages."""
    schema = load_json(schema_path)
    document = load_json(document_path)

    validator = Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)
    errors = []
    for error in sorted(validator.iter_errors(document), key=lambda e: list(e.absolute_path)):
        path = ".".join(str(p) for p in error.absolute_path) or "(root)"
        errors.append(f"  {path}: {error.message}")
    return errors


def validate_all_schemas(schema_dir: str, document_dir: str) -> dict:
    """Validate all documents in a directory against matching schemas."""
    results = {}
    schema_dir = Path(schema_dir)
    document_dir = Path(document_dir)

    for doc_path in sorted(document_dir.glob("*.json")):
        for schema_path in schema_dir.glob("*.schema.json"):
            schema_name = schema_path.stem.replace(".schema", "")
            if schema_name in doc_path.stem:
                errors = validate_document(str(schema_path), str(doc_path))
                results[f"{doc_path.name} vs {schema_path.name}"] = errors
                break

    return results


def main():
    parser = argparse.ArgumentParser(description="Validate against node1-governance-kernel schemas")
    parser.add_argument("--all-schemas", nargs=2, metavar=("SCHEMA_DIR", "DOC_DIR"),
                        help="Validate all documents in DOC_DIR against matching schemas in SCHEMA_DIR")
    parser.add_argument("schema", nargs="?", help="Path to JSON Schema file")
    parser.add_argument("document", nargs="?", help="Path to JSON document to validate")
    args = parser.parse_args()

    if args.all_schemas:
        results = validate_all_schemas(args.all_schemas[0], args.all_schemas[1])
        any_fail = False
        for pair, errors in results.items():
            if errors:
                any_fail = True
                print(f"FAIL: {pair} — {len(errors)} error(s):")
                for err in errors:
                    print(err)
            else:
                print(f"PASS: {pair}")
        sys.exit(1 if any_fail else 0)

    if not args.schema or not args.document:
        parser.error("schema and document are required (or use --all-schemas)")

    errors = validate_document(args.schema, args.document)
    if errors:
        print(f"FAIL: {len(errors)} validation error(s):")
        for err in errors:
            print(err)
        sys.exit(1)
    else:
        print("PASS: document is valid")
        sys.exit(0)


if __name__ == "__main__":
    main()
