# Contributing to node1-governance-kernel

Thank you for your interest in contributing! This project aims to make AI agent governance enforceable at the OS level.

## Getting Started

1. Fork the repository
2. Clone your fork
3. Install dependencies: `pip install jsonschema pytest`
4. Run conformance tests: `cd tests/conformance && python -m pytest -v`

## What We Need Help With

### High Priority
- **Adapter implementations**: Cursor, Aider, Continue, and other AI coding agents
- **Windows sandbox**: AppContainer equivalent of the Linux AppArmor profiles
- **Conformance tests**: edge cases, adversarial inputs, boundary conditions

### Medium Priority
- **Documentation**: deployment guides, architecture explainers, translations
- **Schema extensions**: proposals for new schema fields or new schema types
- **Integration tests**: multi-process test scenarios

## Code Style

- Python 3.10+ with type hints
- No external dependencies in `src/` beyond the standard library (except `jsonschema` for the validator)
- Tests use `pytest`

## Submitting Changes

1. Create a branch from `main`
2. Make your changes
3. Ensure all conformance tests pass
4. Submit a pull request with:
   - What you changed and why
   - Which schema(s) or component(s) are affected
   - How to test the change

## Schema Changes

Schema changes require extra care:
- All changes must be backward-compatible (new optional fields only)
- Breaking changes require a version bump and migration guide
- Every schema field must have a `description`
- Conformance tests must cover both valid and invalid cases

## Security Issues

If you discover a security vulnerability, please report it privately. Do NOT open a public issue. Contact: security@node1.ai

## License

By contributing, you agree that your contributions will be licensed under the Apache License 2.0.
