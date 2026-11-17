# Claude Code MCP Adapter

Runnable MCP proxy for Claude Code. Claude calls one MCP tool,
`governed_tool_call`; the adapter requests broker admission over AF_UNIX,
forwards only admitted calls to an upstream stdio MCP server, and persists an
Evidence Manifest v1 for admitted, blocked, invalid, timeout, and upstream-error
paths.

## Requirements

- Python 3.10+
- `mcp` Python SDK; verified with 2.2.0, with a compatibility import path for 1.x
- Linux, macOS, or WSL2 for the real AF_UNIX broker

```bash
python -m pip install mcp
```

No dependency other than the standard library and `mcp` is used by this
adapter.

## Mock mode

Start the MCP server with a deterministic offline broker and forwarder:

```bash
NODE1_MOCK_BROKER=1 python examples/claude-code/claude_code_mcp_adapter.py
```

or:

```bash
python examples/claude-code/claude_code_mcp_adapter.py --mock
```

Mock output is explicitly marked as offline and is not live broker evidence.

## Real broker and upstream MCP server

Configure the broker plus the stdio MCP server that owns the actual tools:

```bash
export NODE1_BROKER_SOCKET=/run/node1/broker/broker.sock
export NODE1_EVIDENCE_DIR=./evidence/claude-code
export NODE1_UPSTREAM_COMMAND=python
export NODE1_UPSTREAM_ARGS='["path/to/upstream_server.py"]'
python examples/claude-code/claude_code_mcp_adapter.py
```

Optional upstream settings:

- `NODE1_UPSTREAM_CWD`: working directory for the upstream server.
- `NODE1_UPSTREAM_ENV`: JSON object of string environment values.
- `NODE1_UPSTREAM_ARGS`: JSON list of command arguments.

The adapter opens a fresh upstream MCP session for each admitted call. This is
simple and isolates failures; a production deployment may add a supervised
session pool without changing the broker admission contract.

## Claude Code configuration

```json
{
  "mcpServers": {
    "node1-governance": {
      "command": "python",
      "args": [
        "/absolute/path/to/examples/claude-code/claude_code_mcp_adapter.py"
      ],
      "env": {
        "NODE1_BROKER_SOCKET": "/run/node1/broker/broker.sock",
        "NODE1_EVIDENCE_DIR": "/absolute/path/to/evidence/claude-code",
        "NODE1_UPSTREAM_COMMAND": "python",
        "NODE1_UPSTREAM_ARGS": "[\"/absolute/path/to/upstream_server.py\"]"
      }
    }
  }
}
```

Claude then invokes:

```json
{
  "tool_name": "read_file",
  "tool_args": {"path": "README.md"}
}
```

The MCP tool returns a JSON text document containing `status`, `admitted`, the
upstream result, and the evidence manifest/path. Returning JSON text avoids the
structured-result conversion mismatch observed with MCP SDK 2.2.0 and the
installed Pydantic version; the 1.x import path is present but was not exercised
in this build environment.

The proxy sends only the tool name and canonical argument hash to the broker.
If `admitted` is false or the response is malformed/timed out, the upstream
server is not started and the call fails closed. If the upstream tool fails,
the manifest records `admitted: true` with `verdict: ERROR`.

## Run tests

```bash
python -m unittest -v examples/claude-code/test_claude_code_adapter.py
```

The suite covers forwarding, blocking without forwarding, malformed broker
responses, timeout, upstream failure, evidence format/hashes, invalid input,
and MCP tool registration.
