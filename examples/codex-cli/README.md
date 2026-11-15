# Codex CLI Adapter — Reference Example

Demonstrates the broker communication protocol using the governance kernel's IPC frames.

> **Note**: This is a reference implementation showing how to request admission and write evidence manifests. It does not wrap Codex CLI end-to-end; a production adapter would hook into Codex's tool execution pipeline.

## What the Code Does

`codex_adapter.py` shows:

1. Connecting to the governance broker via AF_UNIX socket
2. Sending an admission request with a tool name and argument hash
3. Receiving an admission response (admitted/blocked)
4. Generating an evidence manifest for the completed call

## Files

- `codex_adapter.py` — Reference broker communication example

## Running

```bash
export NODE1_BROKER_SOCKET=/run/node1/broker/broker.sock
python codex_adapter.py
```

The script connects to the broker, requests admission for a sample `read_file` call, and prints the evidence manifest. A running broker is required.
