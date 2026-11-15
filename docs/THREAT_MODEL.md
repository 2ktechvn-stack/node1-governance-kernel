# Threat Model

## Trust Principals

| Principal | Unix User | Trust Level | Can Access |
|-----------|-----------|-------------|------------|
| Agent | `node1-agent` | Untrusted | Workspace files (via broker), broker socket |
| Broker | `node1-broker` | Semi-trusted | Agent socket, governance socket, workspace files |
| Governance | `node1-governance` | Trusted | Audit log, evidence store, governance socket |

## Threat Categories

### T1: Agent Bypasses Broker

**Attack**: Agent directly accesses files, network, or governance without going through the broker.

**Mitigation**: AppArmor profile confines agent to workspace read + broker socket only. No raw network, no direct file write outside workspace, no `execve` of arbitrary binaries.

### T2: Agent Impersonates Broker

**Attack**: Agent connects to governance socket pretending to be the broker.

**Mitigation**: Governance socket is `0660` owned by `node1-governance:node1-governance-ipc`. Only the broker user (member of `node1-governance-ipc` group) can connect. Agent user is NOT in this group. `SO_PEERCRED` verifies the UID on every connection.

### T3: Agent Modifies Audit Log

**Attack**: Agent deletes or alters evidence manifests to hide actions.

**Mitigation**: Evidence store is owned by `node1-governance` user. Agent has no write access. Broker writes evidence through governance daemon only.

### T4: Path Traversal

**Attack**: Agent requests `../../etc/shadow` through broker's file read.

**Mitigation**: Broker resolves all paths with `os.path.realpath()` + `os.path.commonpath()` check against workspace root. Symlinks are resolved before the check.

**Known gap (M4)**: TOCTOU race between `realpath()` and `open()` — an attacker could swap a symlink between the two calls. Mitigation planned for M4: `O_NOFOLLOW` + `/proc/self/fd` pattern.

### T5: Denial of Service

**Attack**: Agent floods broker with connections to exhaust resources.

**Mitigation**: Broker enforces `MAX_CONCURRENT = 32` connections via semaphore. Excess connections receive `OVERLOADED` response. Socket has `settimeout(30)` to prevent hanging connections.

### T6: Frame Injection

**Attack**: Agent sends oversized or pipelined frames to confuse broker.

**Mitigation**: Protocol enforces `MAX_FRAME = 65536` bytes. Pipelined frames (multiple objects in one connection) are rejected. Only JSON objects (not arrays or primitives) are accepted.

### T7: Privilege Escalation via systemd

**Attack**: Agent manipulates systemd to gain broker or governance privileges.

**Mitigation**: Agent has no access to systemd control socket. Service files use `ProtectSystem=strict`, `ProtectHome=yes`, `NoNewPrivileges=yes`.

## Out of Scope (This Version)

- **Network-level attacks**: the kernel assumes a single-machine deployment; network isolation is the deployer's responsibility
- **Kernel exploits**: if the attacker has a Linux kernel exploit, OS-level isolation is moot
- **Supply chain attacks on Python**: the governance daemon trusts its own Python interpreter
- **Side-channel attacks**: timing attacks on HMAC are mitigated by `hmac.compare_digest`, but other side channels are not addressed

## Residual Risks

1. **TOCTOU in path resolution** (T4) — planned fix in M4
2. **WSL2 test mode** — `NODE1_TEST_MODE=1` relaxes UID checks; production deployments must never set this
3. **Python interpreter trust** — governance daemon assumes its Python is not tampered with
