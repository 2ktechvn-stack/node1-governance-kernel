#!/usr/bin/env python3
"""Length-bounded newline-delimited JSON frames with directional HMAC.

Every IPC message between broker, governance, and agent is a single JSON
object terminated by newline, capped at MAX_FRAME bytes. Optional HMAC
signing provides integrity verification between trust principals.
"""
import hashlib
import hmac
import json
import time

MAX_FRAME = 65536


def canonical(value: dict) -> bytes:
    """Deterministic JSON serialization for signing."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")


def sign(key: bytes, value: dict) -> str:
    """HMAC-SHA256 of canonical JSON."""
    return hmac.new(key, canonical(value), hashlib.sha256).hexdigest()


def verify(key: bytes, value: dict, signature: str) -> bool:
    """Constant-time HMAC verification."""
    return hmac.compare_digest(sign(key, value), str(signature))


def send_frame(sock, value: dict) -> None:
    """Send a single JSON frame over a socket."""
    payload = canonical(value) + b"\n"
    if len(payload) > MAX_FRAME:
        raise ValueError("frame too large")
    sock.sendall(payload)


RECV_TIMEOUT = 5.0


def recv_frame(sock) -> dict:
    """Receive a single JSON frame from a socket.

    Enforces one-frame-per-connection-turn: after parsing the first
    newline-terminated object, any pipelined data raises ValueError.
    A 5-second timeout prevents connection starvation from slow peers.
    """
    prev_timeout = sock.gettimeout()
    deadline = time.monotonic() + RECV_TIMEOUT
    data = bytearray()
    try:
        while True:
            timeout_left = deadline - time.monotonic()
            if timeout_left <= 0:
                raise TimeoutError("frame reception timed out")
            sock.settimeout(timeout_left)
            remaining = MAX_FRAME + 1 - len(data)
            chunk = sock.recv(min(4096, remaining))
            if not chunk:
                raise EOFError("peer closed")
            data.extend(chunk)
            if len(data) > MAX_FRAME:
                raise ValueError("frame too large")
            if b"\n" in data:
                line, rest = bytes(data).split(b"\n", 1)
                if rest:
                    raise ValueError("multiple/pipelined frames forbidden")
                value = json.loads(line.decode("utf-8"))
                if not isinstance(value, dict):
                    raise ValueError("object required")
                return value
    finally:
        sock.settimeout(prev_timeout)
