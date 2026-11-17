#!/usr/bin/env python3
"""Claude Code MCP proxy guarded by the Node1 governance broker."""
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

try:  # mcp >= 2
    from mcp.server.mcpserver import MCPServer as MCPServerClass
    MCP_SDK_V2 = True
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as MCPServerClass
    MCP_SDK_V2 = False

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


DEFAULT_BROKER_SOCKET = "/run/node1/broker/broker.sock"
DEFAULT_TIMEOUT_SECONDS = 5.0


class AdapterError(RuntimeError):
    pass


class BrokerTimeoutError(AdapterError):
    pass


class InvalidBrokerResponse(AdapterError):
    pass


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
    """Offline-only policy for test and local MCP wiring."""

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


def model_to_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True, exclude_none=True)
    if hasattr(value, "dict"):
        return value.dict(by_alias=True, exclude_none=True)
    return {"result": str(value)}


class UpstreamMCPForwarder:
    """Open an upstream stdio MCP session for one admitted call."""

    def __init__(self, command: str, args: list[str] | None = None,
                 env: dict[str, str] | None = None, cwd: str | None = None):
        if not command:
            raise ValueError("upstream MCP command is required")
        self.parameters = StdioServerParameters(
            command=command,
            args=args or [],
            env=env,
            cwd=cwd,
        )

    async def call_tool(self, tool_name: str, tool_args: dict[str, Any]) -> dict[str, Any]:
        async with stdio_client(self.parameters) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                return model_to_json(await session.call_tool(tool_name, tool_args))


class MockToolForwarder:
    async def call_tool(self, tool_name: str, tool_args: dict[str, Any]) -> dict[str, Any]:
        return {
            "content": [{"type": "text", "text": f"mock forwarded {tool_name}"}],
            "isError": False,
            "tool_args_sha256": sha256_json(tool_args),
        }


class ClaudeCodeAdapter:
    def __init__(self, broker: Any, forwarder: Any, evidence_writer: EvidenceWriter):
        self.broker = broker
        self.forwarder = forwarder
        self.evidence_writer = evidence_writer

    async def handle_tool_call(self, tool_name: str,
                               tool_args: Mapping[str, Any]) -> dict[str, Any]:
        started = utc_now()
        call_id = f"claude-{uuid.uuid4().hex}"
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
        status = "error"
        output: dict[str, Any] = {}

        try:
            validate_tool_call(tool_name, tool_args)
            normalized_args = dict(tool_args)
            request["args_sha256"] = sha256_json(normalized_args)
            decision = validate_broker_response(self.broker.request(request), call_id)
            admitted = decision["admitted"]
            commitment = decision.get("governance_commitment", "")
            if not admitted:
                status = "blocked"
                verdict = "BLOCK"
                output = {"reason": decision.get("reason", "blocked by broker")}
            else:
                output = await self.forwarder.call_tool(tool_name, normalized_args)
                is_error = bool(output.get("isError", output.get("is_error", False)))
                status = "error" if is_error else "forwarded"
                verdict = "ERROR" if is_error else "PASS"
        except BaseException as exc:
            output = {"error_type": type(exc).__name__, "message": str(exc)}
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
        finally:
            safe_output = _safe_for_hash(output)
            manifest = build_manifest(
                call_id=call_id,
                tool_name=request["tool"],
                tool_args=dict(tool_args) if isinstance(tool_args, Mapping) else {},
                request_data=request,
                output_data=safe_output,
                admitted=admitted,
                commitment=commitment,
                verdict=verdict,
                timestamp_start=started,
            )
            evidence_path = _safe_evidence_write(self.evidence_writer, manifest)

        return {
            "status": status,
            "admitted": admitted,
            "call_id": call_id,
            "result": output,
            "evidence_manifest": manifest,
            "evidence_path": str(evidence_path),
        }


def parse_json_list(name: str, default: list[str]) -> list[str]:
    raw = os.environ.get(name)
    if raw is None:
        return default
    value = json.loads(raw)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{name} must be a JSON list of strings")
    return value


def parse_json_string_map(name: str) -> dict[str, str] | None:
    raw = os.environ.get(name)
    if raw is None:
        return None
    value = json.loads(raw)
    if not isinstance(value, dict) or not all(
        isinstance(key, str) and isinstance(item, str) for key, item in value.items()
    ):
        raise ValueError(f"{name} must be a JSON object of string values")
    return value


def make_adapter(*, mock: bool = False, evidence_dir: Path | None = None,
                 socket_path: str | None = None,
                 timeout: float = DEFAULT_TIMEOUT_SECONDS) -> ClaudeCodeAdapter:
    use_mock = mock or os.environ.get("NODE1_MOCK_BROKER") == "1"
    broker = MockBrokerClient() if use_mock else UnixBrokerClient(
        socket_path or os.environ.get("NODE1_BROKER_SOCKET", DEFAULT_BROKER_SOCKET), timeout
    )
    if use_mock:
        forwarder = MockToolForwarder()
    else:
        command = os.environ.get("NODE1_UPSTREAM_COMMAND", "")
        forwarder = UpstreamMCPForwarder(
            command=command,
            args=parse_json_list("NODE1_UPSTREAM_ARGS", []),
            env=parse_json_string_map("NODE1_UPSTREAM_ENV"),
            cwd=os.environ.get("NODE1_UPSTREAM_CWD"),
        )
    writer = EvidenceWriter(
        evidence_dir
        or Path(os.environ.get("NODE1_EVIDENCE_DIR", Path.cwd() / "evidence"))
    )
    return ClaudeCodeAdapter(broker, forwarder, writer)


def build_mcp_server(adapter: ClaudeCodeAdapter) -> Any:
    server = MCPServerClass(
        name="node1-governance-claude-code-adapter",
        instructions=(
            "Call governed_tool_call for every upstream tool invocation. "
            "Blocked calls are never forwarded."
        ),
    )

    tool_options: dict[str, Any] = {"name": "governed_tool_call"}
    if MCP_SDK_V2:
        tool_options["structured_output"] = False

    @server.tool(**tool_options)
    async def governed_tool_call(tool_name: str,
                                 tool_args: dict[str, Any]) -> str:
        """Admit a hash-bound tool call, forward it, and persist evidence."""
        result = await adapter.handle_tool_call(tool_name, tool_args)
        return json.dumps(result, sort_keys=True, ensure_ascii=True)

    return server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mock", action="store_true", help="use offline broker and forwarder")
    parser.add_argument("--socket", help="AF_UNIX broker socket path")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument(
        "--transport", choices=("stdio", "sse", "streamable-http"), default="stdio"
    )
    args = parser.parse_args(argv)
    adapter = make_adapter(
        mock=args.mock,
        evidence_dir=args.evidence_dir,
        socket_path=args.socket,
        timeout=args.timeout,
    )
    build_mcp_server(adapter).run(transport=args.transport)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
