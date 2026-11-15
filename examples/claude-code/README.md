# Claude Code Adapter — Design Concept

> **Status**: Design documentation only. No runnable adapter is shipped in this release.

This document describes how a Claude Code adapter **would** integrate with the governance broker via MCP.

## Concept

The adapter would run as an MCP (Model Context Protocol) server between Claude Code and the governance broker:

1. Claude Code discovers tools through the MCP server
2. Each tool call is intercepted and sent to the broker for admission
3. The broker checks governance before allowing execution
4. Evidence manifests are generated for every admitted call

## Target Architecture

```
Claude Code  ──MCP──▶  MCP Adapter  ──AF_UNIX──▶  Broker  ──▶  Governance
                       (MCP server)               (mediator)    (daemon)
```

## Target MCP Configuration

```json
{
  "mcpServers": {
    "node1-governance": {
      "command": "python",
      "args": ["path/to/claude_code_mcp_adapter.py"],
      "env": {
        "NODE1_BROKER_SOCKET": "/run/node1/broker/broker.sock"
      }
    }
  }
}
```

## Contributing

This is one of our highest-priority adapter targets. If you'd like to implement it, see the [Codex CLI adapter](../codex-cli/) for a working reference of broker communication, and open an issue to coordinate.
