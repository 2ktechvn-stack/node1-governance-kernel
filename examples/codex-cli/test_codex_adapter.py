#!/usr/bin/env python3
"""Integration tests for the runnable Codex CLI adapter."""
from __future__ import annotations

import importlib.util
import json
import socket
import tempfile
import threading
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("codex_adapter", HERE / "codex_adapter.py")
assert SPEC and SPEC.loader
adapter_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(adapter_module)

from node1_governance_kernel.protocol.frames import recv_frame, send_frame


class FakeBroker:
    def __init__(self, admitted=True, invalid=False, timeout=False):
        self.admitted = admitted
        self.invalid = invalid
        self.timeout = timeout
        self.requests = []

    def request(self, request):
        self.requests.append(request)
        if self.timeout:
            raise adapter_module.BrokerTimeoutError("test timeout")
        if self.invalid:
            return {"call_id": "wrong", "admitted": "yes"}
        return {
            "call_id": request["call_id"],
            "admitted": self.admitted,
            "governance_commitment": "commit-test",
            "reason": "policy denied" if not self.admitted else "",
        }


class UnixBrokerFixture:
    def __init__(self, directory, admitted=True):
        self.path = str(Path(directory) / "broker.sock")
        self.admitted = admitted
        self.request = None
        self.error = None
        self.ready = threading.Event()

    def __enter__(self):
        def serve():
            try:
                server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                server.bind(self.path)
                server.listen(1)
                self.ready.set()
                conn, _ = server.accept()
                with conn:
                    self.request = recv_frame(conn)
                    send_frame(conn, {
                        "call_id": self.request["call_id"],
                        "admitted": self.admitted,
                        "governance_commitment": "unix-integration",
                        "reason": "fixture block" if not self.admitted else "",
                    })
                server.close()
            except Exception as exc:
                self.error = exc
                self.ready.set()

        self.thread = threading.Thread(target=serve, daemon=True)
        self.thread.start()
        self.ready.wait(3)
        if self.error:
            raise self.error
        return self

    def __exit__(self, *_):
        self.thread.join(3)
        if self.error:
            raise self.error


class CodexAdapterTests(unittest.TestCase):
    def make_adapter(self, broker, evidence_dir):
        return adapter_module.CodexAdapter(
            broker, adapter_module.EvidenceWriter(Path(evidence_dir))
        )

    @unittest.skipUnless(hasattr(socket, "AF_UNIX"), "AF_UNIX unavailable")
    def test_admit_over_real_af_unix_socket(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with UnixBrokerFixture(temp_dir, admitted=True) as fixture:
                broker = adapter_module.UnixBrokerClient(fixture.path, timeout=1)
                result = self.make_adapter(broker, temp_dir).admit_tool_call(
                    "read_file", {"path": "README.md"}
                )
            self.assertTrue(result["admitted"])
            self.assertEqual(result["evidence_manifest"]["verdict"], "PASS")
            self.assertEqual(fixture.request["tool"], "read_file")
            self.assertEqual(len(fixture.request["args_sha256"]), 64)

    def test_block_is_recorded(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            result = self.make_adapter(FakeBroker(admitted=False), temp_dir).admit_tool_call(
                "write_file", {"path": "locked"}
            )
            self.assertFalse(result["admitted"])
            self.assertEqual(result["evidence_manifest"]["verdict"], "BLOCK")
            self.assertIn("policy denied", result["broker_response"]["reason"])

    def test_invalid_response_fails_closed_and_writes_evidence(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            result = self.make_adapter(FakeBroker(invalid=True), temp_dir).admit_tool_call(
                "read_file", {"path": "x"}
            )
            self.assertFalse(result["admitted"])
            self.assertIn("call_id mismatch", result["error"])
            self.assertEqual(result["evidence_manifest"]["verdict"], "ERROR")
            self.assertTrue(Path(result["evidence_path"]).is_file())

    def test_timeout_fails_closed_and_writes_evidence(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            result = self.make_adapter(FakeBroker(timeout=True), temp_dir).admit_tool_call(
                "read_file", {"path": "x"}
            )
            self.assertFalse(result["admitted"])
            self.assertIn("timeout", result["error"])
            self.assertEqual(result["evidence_manifest"]["verdict"], "ERROR")

    def test_evidence_format_and_hashes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            args = {"path": "README.md", "line": 7}
            result = self.make_adapter(FakeBroker(), temp_dir).admit_tool_call(
                "read_file", args
            )
            manifest = result["evidence_manifest"]
            required = {
                "manifest_id", "version", "call_id", "agent_uid", "tool_name",
                "input_sha256", "output_sha256", "governance_commitment",
                "admitted", "timestamp_start", "timestamp_end", "verdict",
            }
            self.assertTrue(required.issubset(manifest))
            for field in ("tool_args_sha256", "input_sha256", "output_sha256"):
                self.assertRegex(manifest[field], r"^[0-9a-f]{64}$")
            self.assertEqual(manifest["tool_args_sha256"], adapter_module.sha256_json(args))
            on_disk = json.loads(Path(result["evidence_path"]).read_text("utf-8"))
            self.assertEqual(on_disk, manifest)

    def test_invalid_tool_name_never_reaches_broker(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            broker = FakeBroker()
            result = self.make_adapter(broker, temp_dir).admit_tool_call("", {})
            self.assertEqual(broker.requests, [])
            self.assertEqual(result["evidence_manifest"]["verdict"], "ERROR")

    def test_mock_policy_admits_and_blocks_deterministically(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            adapter = self.make_adapter(adapter_module.MockBrokerClient(), temp_dir)
            admitted = adapter.admit_tool_call("read_file", {"path": "x"})
            blocked = adapter.admit_tool_call("delete_file", {"path": "x"})
            self.assertTrue(admitted["admitted"])
            self.assertFalse(blocked["admitted"])
            self.assertEqual(len(list(Path(temp_dir).glob("EVM-*.json"))), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
