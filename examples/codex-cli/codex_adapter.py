#!/usr/bin/env python3
"""Runnable Codex CLI adapter for the Node1 governance broker.

The adapter sends a hash-bound admission request over AF_UNIX and writes one
schema-compatible evidence manifest for every attempted call. Mock mode is
offline-only and never claims that a real broker admitted an action.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from node1_governance_kernel.protocol.frames import canonical, recv_frame, send_frame


DEFAULT_BROKER_SOCKET = "/run/node1/broker/broker.sock"
DEFAULT_TIMEOUT_SECONDS = 5.0


class AdapterError(RuntimeError):
    """Base class for adapter failures that must fail closed."""


class BrokerTimeoutError(AdapterError):
    """The broker did not return a complete response before the deadline."""


class InvalidBrokerResponse(AdapterError):
    """The broker response did not satisfy the admission contract."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_json(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical(dict(value))).hexdigest()


def validate_tool_call(tool_name: str, tool_args: Mapping[str, Any]) -> None:
    if not isinstance(tool_name, str) or not tool_name.strip():
        raise ValueError("tool_name must be a non-empty string")
    if len(tool_name) > 256:
        raise ValueError("tool_name exceeds 256 characters")
    if not isinstance(tool_args, Mapping):
        raise ValueError("tool_args must be a mapping")
    try:
        canonical(dict(tool_args))
    except (TypeError, ValueError) as exc:
        raise ValueError("tool_args must be JSON serializable") from exc


def validate_broker_response(response: Any, expected_call_id: str) -> dict[str, Any]:
    if not isinstance(response, dict):
        raise InvalidBrokerResponse("broker response must be an object")
    if response.get("call_id") != expected_call_id:
        raise InvalidBrokerResponse("broker response call_id mismatch")
    if type(response.get("admitted")) is not bool:
        raise InvalidBrokerResponse("broker response admitted must be boolean")
    if "governance_commitment" not in response or not isinstance(response["governance_commitment"], str):
        raise InvalidBrokerResponse("missing or invalid governance_commitment")
    if response["admitted"] and not response["governance_commitment"].strip():
        raise InvalidBrokerResponse("admitted response requires non-empty governance_commitment")
    if not response["admitted"]:
        if "reason" not in response or not isinstance(response["reason"], str):
            raise InvalidBrokerResponse("blocked response requires a string reason")
    return response


class UnixBrokerClient:
    """One-request-per-connection AF_UNIX broker client."""

    def __init__(self, socket_path: str, timeout: float = DEFAULT_TIMEOUT_SECONDS):
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.socket_path = socket_path
        self.timeout = timeout

    def request(self, request: dict[str, Any]) -> dict[str, Any]:
        conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        conn.settimeout(self.timeout)
        try:
            conn.connect(self.socket_path)
            send_frame(conn, request)
            return recv_frame(conn)
        except (socket.timeout, TimeoutError) as exc:
            raise BrokerTimeoutError("broker admission timed out") from exc
        except OSError as exc:
            raise AdapterError(f"broker transport failed: {exc}") from exc
        finally:
            conn.close()


class MockBrokerClient:
    """Deterministic offline broker used by tests and ``--mock``."""

    def request(self, request: dict[str, Any]) -> dict[str, Any]:
        tool_name = request["tool"]
        blocked = tool_name.startswith(("block", "deny")) or tool_name in {
            "delete_file",
            "shell.exec.dangerous",
        }
        return {
            "call_id": request["call_id"],
            "admitted": not blocked,
            "governance_commitment": "mock-offline-not-live-authority",
            "reason": "blocked by deterministic mock policy" if blocked else "",
        }


class EvidenceWriter:
    """Create-new writer for evidence manifests."""

    def __init__(self, evidence_dir: Path):
        self.evidence_dir = Path(evidence_dir)

    def write(self, manifest: dict[str, Any]) -> Path:
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        for _ in range(10):
            path = self.evidence_dir / f"{manifest['manifest_id']}.json"
            try:
                with path.open("x", encoding="utf-8", newline="\n") as handle:
                    json.dump(manifest, handle, sort_keys=True, indent=2, ensure_ascii=True)
                    handle.write("\n")
                return path
            except FileExistsError:
                manifest["manifest_id"] = f"EVM-{uuid.uuid4().hex}"
        raise AdapterError("could not allocate a unique evidence manifest path")


def build_manifest(
    *, call_id: str, tool_name: str, tool_args: Mapping[str, Any],
    request_data: Mapping[str, Any], output_data: Mapping[str, Any],
    admitted: bool, commitment: str, verdict: str, timestamp_start: str,
) -> dict[str, Any]:
    return {
        "manifest_id": f"EVM-{uuid.uuid4().hex}",
        "version": "1.0",
        "call_id": call_id,
        "agent_uid": int(getattr(os, "getuid", lambda: 0)()),
        "tool_name": tool_name,
        "tool_args_sha256": sha256_json(tool_args),
        "input_sha256": sha256_json(request_data),
        "output_sha256": sha256_json(output_data),
        "governance_commitment": commitment,
        "admitted": admitted,
        "timestamp_start": timestamp_start,
        "timestamp_end": utc_now(),
        "verdict": verdict,
    }


def _safe_for_hash(value: Any) -> dict[str, Any]:
    """Ensure value is JSON-serializable for canonical hashing."""
    if isinstance(value, dict):
        try:
            canonical(value)
            return value
        except (TypeError, ValueError):
            pass
    return {"_fallback": str(value)}


def _safe_evidence_write(writer: "EvidenceWriter", manifest: dict[str, Any]) -> Path | str:
    """Best-effort evidence write; returns path or error string."""
    try:
        return writer.write(manifest)
    except Exception as exc:
        import sys
        print(f"EVIDENCE_WRITE_FAILED: {exc}", file=sys.stderr)
        return f"EVIDENCE_WRITE_FAILED: {exc}"


class CodexAdapter:
    def __init__(self, broker: Any, evidence_writer: EvidenceWriter):
        self.broker = broker
        self.evidence_writer = evidence_writer

    def admit_tool_call(self, tool_name: str, tool_args: Mapping[str, Any]) -> dict[str, Any]:
        started = utc_now()
        call_id = f"codex-{uuid.uuid4().hex}"
        request: dict[str, Any] = {
            "op": "execute",
            "call_id": call_id,
            "tool": tool_name if isinstance(tool_name, str) else "<invalid>",
            "args_sha256": "0" * 64,
            "timestamp": started,
        }
        admitted = False
        commitment = ""
        verdict = "ERROR"
        error: Exception | None = None
        response: dict[str, Any] = {}

        try:
            validate_tool_call(tool_name, tool_args)
            request["args_sha256"] = sha256_json(tool_args)
            response = validate_broker_response(self.broker.request(request), call_id)
            admitted = response["admitted"]
            commitment = response.get("governance_commitment", "")
            verdict = "PASS" if admitted else "BLOCK"
        except Exception as exc:
            error = exc
            response = {"error_type": type(exc).__name__, "message": str(exc)}
        finally:
            safe_response = _safe_for_hash(response)
            manifest = build_manifest(
                call_id=call_id,
                tool_name=request["tool"],
                tool_args=dict(tool_args) if isinstance(tool_args, Mapping) else {},
                request_data=request,
                output_data=safe_response,
                admitted=admitted,
                commitment=commitment,
                verdict=verdict,
                timestamp_start=started,
            )
            evidence_path = _safe_evidence_write(self.evidence_writer, manifest)

        result = {
            "admitted": admitted,
            "call_id": call_id,
            "broker_response": response,
            "evidence_manifest": manifest,
            "evidence_path": str(evidence_path),
        }
        if error is not None:
            result["error"] = str(error)
        return result


def make_adapter(*, mock: bool = False, socket_path: str | None = None,
                 timeout: float = DEFAULT_TIMEOUT_SECONDS,
                 evidence_dir: Path | None = None) -> CodexAdapter:
    use_mock = mock or os.environ.get("NODE1_MOCK_BROKER") == "1"
    broker = MockBrokerClient() if use_mock else UnixBrokerClient(
        socket_path or os.environ.get("NODE1_BROKER_SOCKET", DEFAULT_BROKER_SOCKET), timeout
    )
    writer = EvidenceWriter(
        evidence_dir
        or Path(os.environ.get("NODE1_EVIDENCE_DIR", Path.cwd() / "evidence"))
    )
    return CodexAdapter(broker, writer)


def parse_json_object(raw: str) -> dict[str, Any]:
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise argparse.ArgumentTypeError("tool arguments must be a JSON object")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mock", action="store_true", help="use deterministic offline broker")
    parser.add_argument("--socket", help="AF_UNIX broker socket path")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--tool", default="read_file")
    parser.add_argument("--args", type=parse_json_object, default={"path": "src/main.py"})
    args = parser.parse_args(argv)

    result = make_adapter(
        mock=args.mock,
        socket_path=args.socket,
        timeout=args.timeout,
        evidence_dir=args.evidence_dir,
    ).admit_tool_call(args.tool, args.args)
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=True))
    if "error" in result:
        return 2
    return 0 if result["admitted"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
