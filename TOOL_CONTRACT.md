# Tool Contract

Every tool must define:

- name
- description
- Pydantic input schema
- Pydantic output schema
- capability
- risk level
- required permission
- timeout seconds
- retry support
- side effects
- undo support
- idempotency key support

Every execution must return:

- structured observation
- evidence references
- started and finished timestamps
- exit status or domain status
- sanitized stdout/stderr or equivalent output
- undo record reference when available

The future PowerShell executor must use explicit executable and arguments with `shell=false`, working directory restrictions, timeout, output size limit, environment allowlist, dangerous pattern detection, risk classification, approval policy, and process tree cleanup.

Phase 2 implements the contract for local filesystem and host whitelist tools. It does not expose raw shell execution.
