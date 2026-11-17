#!/usr/bin/env python3
"""Integration tests for the Claude Code MCP adapter."""
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "claude_code_mcp_adapter", HERE / "claude_code_mcp_adapter.py"
)
assert SPEC and SPEC.loader
adapter_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(adapter_module)


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
            return {"call_id": "wrong", "admitted": True}
        return {
            "call_id": request["call_id"],
            "admitted": self.admitted,
            "governance_commitment": "commit-test",
            "reason": "policy denied" if not self.admitted else "",
        }


class FakeForwarder:
    def __init__(self, fail=False, tool_error=False):
        self.fail = fail
        self.tool_error = tool_error
        self.calls = []

    async def call_tool(self, tool_name, tool_args):
        self.calls.append((tool_name, tool_args))
        if self.fail:
            raise RuntimeError("upstream unavailable")
        return {
            "content": [{"type": "text", "text": "forwarded"}],
            "isError": self.tool_error,
        }


class ClaudeCodeAdapterTests(unittest.IsolatedAsyncioTestCase):
    def make_adapter(self, broker, forwarder, evidence_dir):
        return adapter_module.ClaudeCodeAdapter(
            broker,
            forwarder,
            adapter_module.EvidenceWriter(Path(evidence_dir)),
        )

    async def test_admitted_call_is_forwarded_with_exact_arguments(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            forwarder = FakeForwarder()
            result = await self.make_adapter(FakeBroker(), forwarder, temp_dir).handle_tool_call(
                "read_file", {"path": "README.md"}
            )
            self.assertEqual(result["status"], "forwarded")
            self.assertTrue(result["admitted"])
            self.assertEqual(forwarder.calls, [("read_file", {"path": "README.md"})])
            self.assertEqual(result["evidence_manifest"]["verdict"], "PASS")

    async def test_blocked_call_is_never_forwarded(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            forwarder = FakeForwarder()
            result = await self.make_adapter(
                FakeBroker(admitted=False), forwarder, temp_dir
            ).handle_tool_call("write_file", {"path": "locked"})
            self.assertEqual(result["status"], "blocked")
            self.assertFalse(result["admitted"])
            self.assertEqual(forwarder.calls, [])
            self.assertEqual(result["evidence_manifest"]["verdict"], "BLOCK")

    async def test_invalid_broker_response_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            forwarder = FakeForwarder()
            result = await self.make_adapter(
                FakeBroker(invalid=True), forwarder, temp_dir
            ).handle_tool_call("read_file", {"path": "x"})
            self.assertEqual(result["status"], "error")
            self.assertFalse(result["admitted"])
            self.assertEqual(forwarder.calls, [])
            self.assertIn("call_id mismatch", result["result"]["message"])

    async def test_broker_timeout_fails_closed_and_writes_evidence(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            result = await self.make_adapter(
                FakeBroker(timeout=True), FakeForwarder(), temp_dir
            ).handle_tool_call("read_file", {"path": "x"})
            self.assertEqual(result["status"], "error")
            self.assertEqual(result["evidence_manifest"]["verdict"], "ERROR")
            self.assertTrue(Path(result["evidence_path"]).is_file())

    async def test_upstream_failure_is_evidenced_after_admission(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            result = await self.make_adapter(
                FakeBroker(), FakeForwarder(fail=True), temp_dir
            ).handle_tool_call("read_file", {"path": "x"})
            self.assertTrue(result["admitted"])
            self.assertEqual(result["status"], "error")
            self.assertEqual(result["evidence_manifest"]["verdict"], "ERROR")
            self.assertIn("upstream unavailable", result["result"]["message"])

    async def test_evidence_format_and_argument_hash(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            args = {"command": "status", "flags": ["--short"]}
            result = await self.make_adapter(
                FakeBroker(), FakeForwarder(), temp_dir
            ).handle_tool_call("git", args)
            manifest = result["evidence_manifest"]
            self.assertRegex(manifest["tool_args_sha256"], r"^[0-9a-f]{64}$")
            self.assertRegex(manifest["input_sha256"], r"^[0-9a-f]{64}$")
            self.assertRegex(manifest["output_sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(manifest["tool_args_sha256"], adapter_module.sha256_json(args))
            self.assertEqual(
                json.loads(Path(result["evidence_path"]).read_text("utf-8")), manifest
            )

    async def test_mcp_server_registers_governed_tool(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            adapter = self.make_adapter(FakeBroker(), FakeForwarder(), temp_dir)
            server = adapter_module.build_mcp_server(adapter)
            tools = await server.list_tools()
            self.assertIn("governed_tool_call", [tool.name for tool in tools])

    async def test_mcp_server_call_end_to_end_in_mock_mode(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            adapter = self.make_adapter(
                adapter_module.MockBrokerClient(),
                adapter_module.MockToolForwarder(),
                temp_dir,
            )
            server = adapter_module.build_mcp_server(adapter)
            result = await server.call_tool(
                "governed_tool_call",
                {"tool_name": "read_file", "tool_args": {"path": "README.md"}},
            )
            normalized = adapter_module.model_to_json(result)
            self.assertFalse(normalized.get("isError", normalized.get("is_error", False)))
            self.assertEqual(len(list(Path(temp_dir).glob("EVM-*.json"))), 1)

    async def test_invalid_tool_name_never_reaches_broker_or_upstream(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            broker = FakeBroker()
            forwarder = FakeForwarder()
            result = await self.make_adapter(broker, forwarder, temp_dir).handle_tool_call(
                "", {}
            )
            self.assertEqual(broker.requests, [])
            self.assertEqual(forwarder.calls, [])
            self.assertEqual(result["evidence_manifest"]["verdict"], "ERROR")


if __name__ == "__main__":
    unittest.main(verbosity=2)
