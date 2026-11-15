# node1-governance-kernel

**Governance runtime for AI agent fleets** — privilege separation, tool allowlisting, and audit evidence that run at the OS level, not inside the AI's own context.

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)

## Problem

AI coding agents (Claude Code, Codex CLI, Cursor, etc.) enforce safety rules by prompting the model to follow them. A sufficiently long conversation, a prompt injection, or a misrouted tool call can bypass every rule — because the rules live in the same address space as the agent.

**node1-governance-kernel** moves enforcement out of the model and into the operating system:

- **Privilege separation**: the agent runs as one Unix user; governance runs as another. The agent *cannot* `rm` the audit log or modify its own allowlist.
- **Broker-mediated access**: every external action (file write, git push, HTTP request, script execution) goes through a broker that checks a governance daemon before proceeding.
- **Structured evidence**: every decision produces a machine-verifiable evidence manifest — not a chat log, but a signed record with hash-bound inputs and outputs.

## Architecture

```
┌─────────────┐     AF_UNIX + peer creds      ┌──────────────┐
│  AI Agent    │ ──────────────────────────────▶│    Broker     │
│ (user: agent)│                                │ (user: broker)│
└─────────────┘                                └──────┬───────┘
                                                      │
                                               AF_UNIX│peer creds
                                                      ▼
                                               ┌──────────────┐
                                               │  Governance   │
                                               │   Daemon      │
                                               │(user: gov)    │
                                               └──────────────┘
```

Three principals, three Unix users, three trust boundaries. The agent never talks to governance directly — the broker mediates and verifies peer credentials on every connection.

> **Platform support:** The daemon uses OS-level peer credential extraction — `SO_PEERCRED` on Linux/WSL2 and `LOCAL_PEERCRED` on macOS. Windows is not supported for the daemon (use WSL2). The CLI validator and JSON schemas work on all platforms.

## Spec Schemas

The kernel defines five JSON schemas that any adapter must produce:

| Schema | Purpose |
|--------|---------|
| **Task Packet** | Structured work unit with scope, risk classification, and acceptance criteria |
| **Risk Boundary** | Safety fence: money, secrets, legal, go-live, delete, OS-change — actions requiring human approval |
| **Plan Baseline** | Hash-bound execution plan approved before build starts |
| **Evidence Manifest** | 12-field record with input/output hashes, timestamps, and governance commitment |
| **Independence Receipt** | Proof that a review came from a verified-independent reviewer |

Schemas live in [`schemas/`](schemas/) as JSON Schema (draft 2020-12).

## Quick Start

### Validate a Task Packet

```bash
pip install -e ".[validator]"
python -m node1_governance_kernel.validator schemas/task_packet.schema.json my_packet.json
```

### Run Conformance Tests

```bash
cd tests/conformance
python -m pytest -v
```

### Adapter Examples

- **Codex CLI**: [`examples/codex-cli/`](examples/codex-cli/) — reference demo of broker communication protocol
- **Claude Code**: [`examples/claude-code/`](examples/claude-code/) — design concept (contribution target, not yet implemented)

## Project Structure

```
src/
  node1_governance_kernel/
    __init__.py
    validator.py       # Schema validator CLI
    protocol/
      frames.py        # Length-bounded JSON frame protocol
      peer.py          # SO_PEERCRED peer credential extraction
schemas/               # JSON Schema definitions for the 5 spec schemas
tests/
  conformance/         # Schema conformance test suite
examples/
  codex-cli/           # Codex CLI adapter reference (broker communication demo)
  claude-code/         # Claude Code adapter design concept (not yet implemented)
docs/                  # Threat model
```

## Requirements

- Python 3.10+
- Linux with AF_UNIX + SO_PEERCRED support (WSL2 works for development)
- systemd (for production deployment; not required for testing)

## Security Model

The kernel's security **design** relies on OS-level isolation, not model compliance. This repo ships the spec schemas, IPC protocol, and conformance tests; the enforcing daemons and AppArmor profiles are part of the deployment (not yet open-sourced):

1. **User separation** (design): `node1-agent`, `node1-broker`, `node1-governance` are distinct Unix users
2. **Socket DAC** (design): governance socket is `0660` owned by `node1-governance:node1-governance-ipc`
3. **AppArmor profiles** (planned): agent confinement — no raw network, no direct file access outside workspace
4. **Peer credential verification** (shipped): `SO_PEERCRED` on every connection — see `src/node1_governance_kernel/protocol/peer.py`

See [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md) for the full threat model.

## Roadmap

- [x] M1: Privilege separation foundation (evidence daemon, governance daemon)
- [x] M2: Sandbox + tool allowlist (broker, AppArmor, path jail)
- [ ] M3: Open source launch (this repo — schemas, protocol, conformance tests)
- [ ] M4: Control Plane (dashboard, SSO, compliance mapping) — commercial

## Contributing

We welcome contributions! Please see [`CONTRIBUTING.md`](CONTRIBUTING.md) for guidelines.

Key areas where help is needed:
- Adapter implementations for other AI agents (Cursor, Aider, Continue, etc.)
- Windows AppContainer equivalent of the Linux sandbox
- Additional conformance test cases
- Documentation translations

## License

Apache License 2.0 — see [LICENSE](LICENSE).

**Open Core model**: this kernel repo is fully open. The Control Plane (dashboard, SSO, audit UI, compliance mapping) is a separate commercial product.

---

Built by [Node1 AI](https://node1.ai) — governance runtime for AI agent fleets.
