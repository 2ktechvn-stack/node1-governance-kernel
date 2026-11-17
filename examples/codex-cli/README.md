# Codex CLI Adapter

Runnable AF_UNIX client for the Node1 governance broker. Every attempted tool
call sends the tool name and canonical argument SHA-256 to the broker, fails
closed on malformed/timeout responses, and persists an Evidence Manifest v1.

## Requirements

- Python 3.10+
- Linux, macOS, or WSL2 for the real AF_UNIX broker
- The repository source tree; no adapter-specific package is required

## Run with the offline mock broker

From the repository root:

```bash
NODE1_MOCK_BROKER=1 python examples/codex-cli/codex_adapter.py \
  --tool read_file --args '{"path":"README.md"}'
```

The equivalent explicit flag is:

```bash
python examples/codex-cli/codex_adapter.py --mock
```

The mock admits ordinary tool names and blocks names beginning with `block` or
`deny`, plus `delete_file` and `shell.exec.dangerous`. Its commitment is marked
`mock-offline-not-live-authority`; it is test evidence, not proof of a daemon or
live policy decision.

## Run against a real broker

```bash
export NODE1_BROKER_SOCKET=/run/node1/broker/broker.sock
export NODE1_EVIDENCE_DIR=./evidence/codex
python examples/codex-cli/codex_adapter.py \
  --tool read_file --args '{"path":"README.md"}'
```

Optional flags:

- `--socket PATH`: override `NODE1_BROKER_SOCKET`.
- `--timeout SECONDS`: broker timeout; default 5 seconds.
- `--evidence-dir DIR`: override `NODE1_EVIDENCE_DIR`.
- `--tool NAME` and `--args JSON_OBJECT`: describe the proposed call.

Exit codes are `0` admitted, `3` blocked, and `2` invalid/transport/error.
The JSON output contains the decision, manifest, and persisted evidence path.
The adapter only performs admission; the Codex tool host remains responsible
for executing admitted actions and may use `build_manifest` for final output
evidence when integrating this module into a full execution pipeline.

## Run tests

```bash
python -m unittest -v examples/codex-cli/test_codex_adapter.py
```

The suite covers real AF_UNIX framing, admit, block, malformed response,
timeout, invalid input, deterministic mock policy, and evidence hashes/format.

## Admission frame

```json
{
  "op": "execute",
  "call_id": "codex-<uuid>",
  "tool": "read_file",
  "args_sha256": "<canonical-json-sha256>",
  "timestamp": "<UTC ISO-8601>"
}
```

The response must echo `call_id`, contain a boolean `admitted`, and use a
string `governance_commitment`. Any mismatch is an error and fails closed.
