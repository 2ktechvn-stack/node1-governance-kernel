#!/usr/bin/env python3
"""Example adapter: Codex CLI → node1-governance-kernel broker.

This adapter demonstrates how to wrap an AI agent's tool calls through
the governance broker. It is a reference implementation, not production code.
"""
import hashlib
import json
import os
import socket
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))
from node1_governance_kernel.protocol.frames import send_frame, recv_frame, canonical


BROKER_SOCKET = os.environ.get("NODE1_BROKER_SOCKET", "/run/node1/broker/broker.sock")


def connect_broker():
    """Connect to the governance broker."""
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(10)
    sock.connect(BROKER_SOCKET)
    return sock


def request_admission(tool_name: str, tool_args: dict) -> dict:
    """Request governance admission for a tool call.

    Returns the broker's response, which includes:
    - admitted: bool
    - call_id: str (for evidence tracking)
    - governance_commitment: str
    - reason: str (if blocked)
    """
    call_id = f"codex-{uuid.uuid4().hex[:12]}"
    args_sha = hashlib.sha256(canonical(tool_args)).hexdigest()

    request = {
        "op": "execute",
        "call_id": call_id,
        "tool": tool_name,
        "args_sha256": args_sha,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    conn = connect_broker()
    try:
        send_frame(conn, request)
        response = recv_frame(conn)
    finally:
        conn.close()

    return response


def write_evidence(call_id: str, tool_name: str, input_data: dict,
                   output_data: dict, admitted: bool, commitment: str) -> dict:
    """Write an evidence manifest for a completed tool call."""
    now = datetime.now(timezone.utc).isoformat()
    manifest = {
        "manifest_id": f"EVM-{uuid.uuid4().hex[:8]}",
        "version": "1.0",
        "call_id": call_id,
        "agent_uid": getattr(os, "getuid", lambda: 0)(),
        "tool_name": tool_name,
        "input_sha256": hashlib.sha256(canonical(input_data)).hexdigest(),
        "output_sha256": hashlib.sha256(canonical(output_data)).hexdigest(),
        "governance_commitment": commitment,
        "admitted": admitted,
        "timestamp_start": now,
        "timestamp_end": now,
        "verdict": "PASS" if admitted else "BLOCK",
    }
    return manifest


def main():
    """Demo: request admission for a file read, then write evidence."""
    print("node1-governance-kernel Codex CLI adapter example")
    print(f"Broker socket: {BROKER_SOCKET}")
    print()

    tool_name = "read_file"
    tool_args = {"path": "src/main.py"}

    print(f"Requesting admission for: {tool_name}({tool_args})")
    response = request_admission(tool_name, tool_args)

    if response.get("admitted"):
        print(f"  ADMITTED (call_id={response.get('call_id')})")
        output = {"content": "# file contents would go here"}
        manifest = write_evidence(
            call_id=response["call_id"],
            tool_name=tool_name,
            input_data=tool_args,
            output_data=output,
            admitted=True,
            commitment=response.get("governance_commitment", ""),
        )
        print(f"  Evidence manifest: {json.dumps(manifest, indent=2)}")
    else:
        print(f"  BLOCKED: {response.get('reason', 'no reason given')}")


if __name__ == "__main__":
    main()
