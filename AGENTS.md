# AGENTS.md — Instructions for AI coding agents

This file tells coding agents (and new contributors) how to work in the MConn repository. Read it fully before changing anything.

## 1. What this project is

MConn sends files from an Android phone to a chosen folder on a Windows PC, with offline queuing and automatic acceptance from a paired phone. No cloud file storage.

Read in this order:

1. [README.md](README.md): overview
2. [ARCHITECTURE.md](ARCHITECTURE.md): components, ownership, security, decisions
3. [DESIGN.md](DESIGN.md): behaviour, protocol, API, file handling
4. [DATABASE.mmd](DATABASE.mmd): data models for both sides
5. [ROADMAP.md](ROADMAP.md): current phase and exit criteria

If code and these documents disagree, **stop and flag it**. Do not silently pick one. Update the document in the same change when a design decision genuinely changes.

## 2. Repository map

```
android/app/{share,pairing,transfer,queue,ui}/   Kotlin, Jetpack Compose, Room, WorkManager
windows-receiver/{api,pairing,transfer,storage,database}/  + main.py   Python, FastAPI, SQLite
protocol/transfer-contracts.md                   Source of truth for the wire contract
tests/{integration,failure-recovery}/            Cross-component tests
```

Module boundaries are intentional: **networking, transfer state and filesystem operations stay separate.** Do not let UI code touch HTTP, or API handlers touch the filesystem directly. The remote transport must stay replaceable.

## 3. Hard invariants (never violate)

These protect users' data and security. A change that breaks one is wrong even if tests pass.

1. **The PC chooses every destination path.** The phone never sends a path, and the receipt never returns an absolute path.
2. **Never overwrite an existing file in the inbox.** Conflicts get a numeric suffix.
3. **Commit is atomic.** Upload to staging, verify size and SHA-256, then move with `os.replace` on the same volume. No partially written file may ever appear in the inbox.
4. **Transfer ID is the idempotency key.** Re-sending a committed ID returns the stored receipt and creates nothing.
5. **The phone deletes its private copy only after a valid receipt**, and after the retention delay.
6. **Never execute, open, parse or scan received files.** Store only.
7. **All `/v1` endpoints except pairing claim require an active, non-revoked device** with a valid signature, fresh timestamp and unused nonce.
8. **Pin the receiver certificate fingerprint on the phone.** Never disable certificate validation, even "temporarily" or in debug builds. Use a properly configured test fixture instead.
9. **Never log file contents, private keys, pairing tokens or signatures.**
10. **Bind the receiver to LAN and private-network interfaces only**, never blindly to `0.0.0.0` on public interfaces.
11. **Sanitise every filename** as specified in DESIGN.md §6. Treat the phone's name as untrusted input.
12. **Room is the phone's source of truth.** No transfer state lives only in memory or in a worker's arguments.

## 4. Working agreements

- **Work in the current roadmap phase.** Do not build Phase 3 or 4 features during Phase 1. If you spot something needed earlier, raise it.
- **Keep changes small and focused.** One concern per change, with tests.
- **Prefer simple over clever.** Do not invent a networking protocol, a custom crypto scheme, or a relay service. Use the standard pieces named in ARCHITECTURE.md.
- **Do not add dependencies casually.** State why, check maintenance and licence, and prefer the standard library or an existing dependency.
- **Do not claim something works unless you ran it.** Report what you ran and what you did not.
- **Do not fabricate endpoints, library APIs or commands.** Verify against the code or documentation. Anything in the docs marked *(proposed)* is a default, not a verified fact.
- **Ask when a decision is not covered.** Examples: minimum Android version, admin UI approach, default limits (ARCHITECTURE.md §11).

## 5. Conventions

### Python (windows-receiver)

- Python version: pin in `pyproject.toml` once chosen.
- Type hints on all public functions. Format and lint with the tools configured in the repo (to be set up in Phase 0).
- Async handlers must not block the event loop: stream uploads in chunks, run blocking file or hash work in a thread pool when large.
- Database access only through the `database` module; schema changes only through numbered migrations, mirrored in DATABASE.mmd.
- Return errors in the documented shape: `{"error": CODE, "message": ..., "retryable": bool}`.

### Kotlin (android)

- Single-activity Compose UI, unidirectional state flow, no business logic in composables.
- All transfer work goes through WorkManager workers that read and write Room.
- Use `ContentResolver` for shared URIs; do not request broad storage permissions.
- Keys live in Android Keystore and are non-exportable.
- Network calls and hashing run off the main thread.

### Protocol

- `protocol/transfer-contracts.md` is the source of truth. Change the contract first, then both sides, in the same change.
- Backward compatibility: routes are versioned under `/v1`. Additive changes only within a version.

### Commits and reviews

- Imperative, descriptive commit messages (`Add hash verification to commit step`).
- Reference the roadmap phase or design section where useful.
- Update docs when behaviour, schema or contract changes.

## 6. Testing expectations

| Level | What to test |
| --- | --- |
| Unit (PC) | Filename sanitising (reserved names, traversal, unicode, length), conflict suffixing, signature and nonce checks, offset logic, receipt idempotency |
| Unit (Android) | State machine transitions, backoff calculation, queue persistence |
| Integration | Pair → send → verify bytes and hash; unpaired and revoked rejection; duplicate transfer ID |
| Failure recovery | Kill network mid-upload, restart receiver mid-upload, kill the app, lose the receipt, hash mismatch |

Rules:

- Every bug fix gets a regression test.
- Failure-recovery tests assert on end state (exactly one correct file, no leftovers in staging), not just "no exception".
- Hash-verify delivered files byte for byte in integration tests.
- Do not mark an exit criterion in ROADMAP.md as done without evidence.

## 7. Commands

Commands are **to be filled in during Phase 0**, once scaffolding exists. Do not assume any command works until it is listed here.

| Task | Command |
| --- | --- |
| Run receiver | _TBD_ |
| Run PC tests | _TBD_ |
| Build Android app | _TBD_ |
| Run Android tests | _TBD_ |
| Run integration tests | _TBD_ |
| Lint and format | _TBD_ |

## 8. Definition of done

A change is done when:

- [ ] It satisfies the relevant section of DESIGN.md and breaks none of the invariants in §3.
- [ ] New and existing tests pass, and failure paths are tested.
- [ ] Documentation and the protocol contract are updated if behaviour or schema changed.
- [ ] No secrets, personal paths or debugging shortcuts are committed.
- [ ] The change summary states what was verified and what was not.

## 9. When to stop and ask

Pause and ask the maintainer before:

- Changing the wire protocol, authentication scheme or database schema in a way not described in the docs.
- Weakening any invariant in §3.
- Adding network-facing endpoints not listed in DESIGN.md §5.2.
- Introducing a cloud service, third-party relay or account requirement.
- Deleting or migrating user data.
